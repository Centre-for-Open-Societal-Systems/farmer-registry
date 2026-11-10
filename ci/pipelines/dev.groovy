def call() {
pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 60, unit: 'MINUTES')
    }
    environment {
        AWS_REGION = 'ap-south-1'
        ECR_REPOSITORY = 'openg2p/farmer-registry'
        HELM_RELEASE = 'farmer-registry'
        HELM_NAMESPACE = 'farmer'
        KUBECONFIG_CREDENTIAL = 'farmer-dev-kubeconfig'
        // GitHub App credential (username + installation token) with Contents and Pull requests write on this repository.
        // "Username with password" for the very last stage: a maintainer account with push access to oan-helm.
        OAN_HELM_FORK_CRED_ID = 'oan-helm-fork-token'
    }
    stages {
        stage('Test') {
            steps {
                checkout scm
                dir('service-outcomes') { deleteDir() }
                script {
                    // checkout scm does not always export GIT_COMMIT globally.
                    // Resolve the actual workspace revision before tagging images.
                    def commit = sh(returnStdout: true, script: 'git rev-parse --verify HEAD').trim()
                    if (!(commit ==~ /[0-9a-f]{40}/)) {
                        error('Could not resolve the checked-out Git commit')
                    }
                    env.IMAGE_TAG = commit.take(12)
                    env.SOURCE_COMMIT = commit
                    // Branch-index builds may not yet have the parameter definition, and a build started
                    // before this change still offers the retired publish-only choice: both mean deploy.
                    env.DELIVERY_ACTION = sh(returnStdout: true,
                        script: 'python3 ci/delivery.py action').trim()
                }
                sh '''
                    set -eu
                    docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                    docker run --rm --user "$(id -u):$(id -g)" \
                      -v "$PWD:/repo:ro" "coss-ci/validation:$IMAGE_TAG" \
                      bash ci/validation/validate.sh
                '''
            }
        }
        stage('Build') {
            steps {
                sh '''
                    set -eu
                    bash ci/build/images.sh "$IMAGE_TAG"
                '''
            }
        }
        stage('Publish') {
            when { allOf { branch 'develop'; not { changeRequest() } } }
            steps {
                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds']]) {
                    script {
                        env.ECR_REGISTRY = sh(returnStdout: true, script: '''
                          set +x
                          account=$(aws sts get-caller-identity --query Account --output text)
                          case "$account" in *[!0-9]*|'') exit 1 ;; esac
                          test "${#account}" = 12
                          printf '%s.dkr.ecr.%s.amazonaws.com' "$account" "$AWS_REGION"
                        ''').trim()
                    }
                    sh '''
                        set -eu
                        set +x
                        export DOCKER_CONFIG
                        DOCKER_CONFIG=$(mktemp -d)
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT
                        aws ecr get-login-password --region "$AWS_REGION" |
                          docker login --username AWS --password-stdin "$ECR_REGISTRY"
                        mkdir -p service-outcomes
                        : > service-outcomes/registry-images.tsv
                        for component in staff-api partner-api celery db-seed sanity-tests staff-ui; do
                          image="$ECR_REGISTRY/$ECR_REPOSITORY/$component:$IMAGE_TAG"
                          docker tag "coss-ci/$component:$IMAGE_TAG" "$image"
                          docker push "$image"
                          digest=$(aws ecr describe-images --region "$AWS_REGION" \
                            --repository-name "$ECR_REPOSITORY/$component" --image-ids "imageTag=$IMAGE_TAG" \
                            --query 'imageDetails[0].imageDigest' --output text)
                          printf '%s\t%s\t%s\n' "$component" "$image" "$digest" >> service-outcomes/registry-images.tsv
                        done
                        # The connector images (docker/registry-connector, docker/registry-connector-ui) are
                        # not registry components, so they get their own outcome file, not registry-images.tsv.
                        : > service-outcomes/registry-connector.tsv
                        for component in registry-connector registry-connector-ui; do
                          repository="$ECR_REPOSITORY/$component"
                          aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$repository" > /dev/null 2>&1 ||
                            aws ecr create-repository --region "$AWS_REGION" --repository-name "$repository" > /dev/null
                          docker tag "coss-ci/$component:$IMAGE_TAG" "$ECR_REGISTRY/$repository:$IMAGE_TAG"
                          docker push "$ECR_REGISTRY/$repository:$IMAGE_TAG"
                          digest=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$repository" \
                            --image-ids "imageTag=$IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text)
                          printf '%s\t%s\t%s\n' "$component" "$ECR_REGISTRY/$repository:$IMAGE_TAG" "$digest" >> service-outcomes/registry-connector.tsv
                          echo "$component: $ECR_REGISTRY/$repository:$IMAGE_TAG@$digest"
                        done
                        docker run --rm --network none --user "$(id -u):$(id -g)" \
                          -e DELIVERY_ACTION \
                          -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT \
                          -v "$PWD:/repo" "coss-ci/validation:$IMAGE_TAG" \
                          python ci/delivery.py publication service-outcomes/publication.json
                    '''
                    // Only the digests, for the stage "Package chart".
                    stash name: 'image-digests', includes: 'service-outcomes/registry-images.tsv'
                }
            }
        }
        stage('Package chart') {
            // helm/openg2p-farmer-registry with this build's images (ci/deploy/package_chart.py). The deploy installs this
            // archive and "Publish chart" publishes the same one, so what runs on New Dev is what oan-helm lists. It needs
            // the git history for the version, so it is not part of the deployment stash.
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION in ['deploy', 'fresh-install'] } }
            }
            agent { label 'oan-ci-deploy' }
            options { timeout(time: 15, unit: 'MINUTES') }
            steps {
                checkout scm
                sh 'mkdir -p service-outcomes && rm -f service-outcomes/registry-images.tsv'
                unstash 'image-digests'
                script {
                    def subject = sh(returnStdout: true, script: 'git log -1 --pretty=%s').trim()
                    withEnv(["COMMIT_SUBJECT=${subject}"]) {
                        sh 'python3 ci/deploy/package_chart.py package'
                    }
                }
                stash name: 'built-chart', includes: 'built-chart/**'
            }
        }
        stage('Deploy (package)') {
            when { allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION != 'publish-only' } } }
            steps {
                stash name: 'dev-deployment', includes: 'helm/**,ci/**,scripts/**,integrations/**,test/runtime/**,service-outcomes/**,farmer-extension/**,ui/staff-ui/overrides/**,docker/**,test/sanity/**', excludes: 'helm/**/charts/**,**/__pycache__/**,**/.pytest_cache/**', useDefaultExcludes: false
            }
        }
        stage('Deploy (registry)') {
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION in ['deploy', 'fresh-install'] } }
            }
            agent { label 'oan-ci-deploy' }
            steps {
                dir('dev-deployment') {
                    deleteDir()
                    unstash 'dev-deployment'
                    unstash 'built-chart'
                    withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                        script {
                          def deployRegistry = {
                            try {
                              if (env.DELIVERY_ACTION == 'fresh-install') {
                                // The database backups go to the dev box over the existing backup key.
                                withCredentials([sshUserPrivateKey(credentialsId: 'farmer-new-dev-backup-ssh', keyFileVariable: 'BACKUP_SSH_KEY')]) {
                                  sh '''
                            set -eu
                            export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                            export BUILT_CHART_DIR="$PWD/built-chart"
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                            bash ci/deploy/fresh-install-dev.sh
                            '''
                                }
                              } else {
                                sh '''
                            set -eu
                            export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                            export BUILT_CHART_DIR="$PWD/built-chart"
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                            bash ci/deploy/deploy-dev.sh
                            '''
                              }
                            } finally {
                              // Retain sanitized failure provenance on the VPN agent too.
                              archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
                            }
                          }
                          withEnv(["APPLY_COMMONS_IDENTITY=${env.APPLY_COMMONS_IDENTITY == 'true'}"]) {
                            if (env.APPLY_COMMONS_IDENTITY == 'true') {
                              withCredentials([file(credentialsId: 'farmer-dev-identity-evidence', variable: 'IDENTITY_EVIDENCE_FILE')]) {
                                deployRegistry()
                              }
                            } else {
                              deployRegistry()
                            }
                          }
                        }
                    }
                    archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
                }
            }
        }
        stage('Build (services)') {
            when { allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' && (env.COORDINATE_SERVICES ?: 'true') != 'false' } } }
            steps {
                // The dashboard API is part of the registry chart this build packaged and "Deploy (registry)" installed;
                // its pin (built-chart/pin.json) replaces ci/deploy/oan-chart.json for both services stages.
                unstash 'built-chart'
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                    withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds']]) {
                        sh '''
                            set -eu
                            set +x
                            export OAN_BUILT_CHART_PIN="$PWD/built-chart/pin.json"
                            bash ci/services/run-container.sh build \
                              --environment dev --registry "$ECR_REGISTRY" --output service-outcomes/build.json
                        '''
                    }
                }
                stash name: 'optional-deployment', includes: 'built-chart/**,ci/**,helm/**,scripts/**,integrations/**,docker/registry-connector-ui/**,test/runtime/**,service-outcomes/build.json', excludes: 'helm/**/charts/**', useDefaultExcludes: false
            }
        }
        stage('Deploy (services)') {
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' && (env.COORDINATE_SERVICES ?: 'true') != 'false' } }
            }
            agent { label 'oan-ci-deploy' }
            steps {
                dir('optional-dev-deployment') {
                    deleteDir()
                    unstash 'optional-deployment'
                    script {
                      env.CONNECTOR_BACKUP_DIRECTORY = "${pwd(tmp: true)}/connector-backup-${env.BUILD_NUMBER}"
                      catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                        withCredentials([sshUserPrivateKey(credentialsId: 'farmer-new-dev-backup-ssh', keyFileVariable: 'BACKUP_SSH_KEY')]) {
                          sh 'bash scripts/operations/connector/fetch-backup-container.sh'
                        }
                      }
                    }
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                        withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                            sh '''
                                set -eu
                                if ! test -d "$CONNECTOR_BACKUP_DIRECTORY"; then unset CONNECTOR_BACKUP_DIRECTORY; fi
                                export OAN_BUILT_CHART_PIN="$PWD/built-chart/pin.json"
                                bash ci/services/run-container.sh deploy \
                                  --environment dev --registry "$ECR_REGISTRY" \
                                  --input service-outcomes/build.json --output service-outcomes/deploy.json
                            '''
                        }
                    }
                    archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
                }
            }
        }
        stage('Publish chart') {
            // The last stage. After the images were pushed AND deployed to New Dev (a failed deploy fails the build, so
            // this stage never runs for it): add the archive of "Package chart" to repository/develop/ of oan-helm. No
            // pull request and no merge: oan-helm's workflow updates the index, the changelog and the rollback history.
            // If publishing fails the stage is UNSTABLE and says why; New Dev already runs the build.
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' } }
            }
            agent { label 'oan-ci-deploy' }
            options { timeout(time: 15, unit: 'MINUTES') }
            steps {
                checkout scm
                sh 'rm -rf built-chart'
                unstash 'built-chart'
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    // A maintainer's token for now; the GitHub App replaces this credential when it is configured.
                    withCredentials([usernamePassword(credentialsId: "${OAN_HELM_FORK_CRED_ID}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                        sh 'python3 ci/deploy/package_chart.py publish'
                    }
                }
            }
        }
    }
    post {
        failure {
            script {
                // Mail the DevOps list and the commit author; a controller without SMTP must not hide the failure.
                try {
                    def author = ''
                    try { author = sh(script: "git log -1 --pretty=format:'%ae'", returnStdout: true).trim() } catch (ignored) { author = '' }
                    def recipients = ['simretyibeltal@gmail.com', 'pavanns.ns@gmail.com']
                    if (author && !author.contains('noreply')) { recipients = [author] + recipients }
                    mail(
                        to: recipients.unique().join(', '),
                        subject: "Build FAILED: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                        body: "Farmer Registry build or deploy failed.\n\nJob:     ${env.JOB_NAME}\nBranch:  ${env.BRANCH_NAME}\nBuild:   #${env.BUILD_NUMBER}\nURL:     ${env.BUILD_URL}\nConsole: ${env.BUILD_URL}console\n\nJenkins"
                    )
                } catch (err) {
                    echo "notification not sent: ${err.message}"
                }
            }
        }
        always {
            archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
            archiveArtifacts artifacts: 'ci-output/native-worker-save/**', allowEmptyArchive: true
        }
    }
}

}
return this
