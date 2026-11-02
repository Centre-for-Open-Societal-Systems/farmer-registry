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
        PIN_PR_CRED_ID = 'oan-ci-app'
        // "Username with password" for the very last stage: the GitHub account that owns the fork of oan-helm and its
        // classic token (public_repo). The image pull request goes from that fork into oan-helm main.
        OAN_HELM_FORK_CRED_ID = 'oan-helm-fork-token'
    }
    parameters {
        choice(name: 'DELIVERY_ACTION', choices: ['deploy', 'fresh-install'],
            description: 'Leave on deploy: every develop build publishes the images and upgrades the existing dev release with them (the pinned chart, the live values), and Helm rolls back to the previous revision if the upgrade fails. fresh-install backs up the dev registry databases, uninstalls the release, drops the databases and installs the pinned chart again on an empty database (all dev farmer data is lost; Commons is untouched).')
        booleanParam(name: 'COORDINATE_SERVICES', defaultValue: false,
            description: 'Build and independently upgrade available optional services; failures mark UNSTABLE.')
        booleanParam(name: 'APPLY_COMMONS_IDENTITY', defaultValue: false,
            description: 'Apply reviewed Commons staff identity values; requires fresh farmer-dev-identity-evidence credential.')
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
                    // Only the digests, for the last stage ("Open oan-helm image PR").
                    stash name: 'image-digests', includes: 'service-outcomes/registry-images.tsv'
                }
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
            agent { label 'vpn-agent2' }
            steps {
                dir('dev-deployment') {
                    deleteDir()
                    unstash 'dev-deployment'
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
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                            bash ci/deploy/fresh-install-dev.sh
                            '''
                                }
                              } else {
                                sh '''
                            set -eu
                            export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                            bash ci/deploy/deploy-dev.sh
                            '''
                              }
                            } finally {
                              // Retain sanitized failure provenance on the VPN agent too.
                              archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
                            }
                          }
                          withEnv(["APPLY_COMMONS_IDENTITY=${params.APPLY_COMMONS_IDENTITY}"]) {
                            if (params.APPLY_COMMONS_IDENTITY) {
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
            when { allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' && params.COORDINATE_SERVICES } } }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                    withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds']]) {
                        sh '''
                            set -eu
                            set +x
                            bash ci/services/run-container.sh build \
                              --environment dev --registry "$ECR_REGISTRY" --output service-outcomes/build.json
                        '''
                    }
                }
                stash name: 'optional-deployment', includes: 'ci/**,helm/**,scripts/**,integrations/**,test/runtime/**,service-outcomes/build.json', excludes: 'helm/**/charts/**', useDefaultExcludes: false
            }
        }
        stage('Deploy (services)') {
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' && params.COORDINATE_SERVICES } }
            }
            agent { label 'vpn-agent2' }
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
        stage('Propose chart pin update') {
            // Last stage: when oan-helm main has a newer Farmer chart than ci/deploy/oan-chart.json, open a pull
            // request to develop that moves the pin. It never deploys and never pushes to develop; a person merges
            // it, and the next develop build deploys it. A failure here marks this stage UNSTABLE and never fails the build.
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' } }
            }
            agent { label 'vpn-agent2' }
            options { timeout(time: 10, unit: 'MINUTES') }
            steps {
                checkout scm
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    withCredentials([usernamePassword(credentialsId: "${PIN_PR_CRED_ID}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                        sh '''
                            set -eu
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                            VALIDATION_IMAGE="coss-ci/validation:$IMAGE_TAG" python3 ci/deploy/propose_pin_pr.py
                        '''
                    }
                }
            }
        }

        stage('Open oan-helm image PR') {
            // The last stage. After the images were pushed AND deployed to New Dev (a failed deploy fails the build, so
            // this stage never runs for it): put this build's image tags and digests into the oan-helm Farmer chart
            // (charts/openg2p-farmer-registry/values.yaml) through a pull request from the fork of oan-helm (GH_USER/oan-helm)
            // into Centre-for-Open-Societal-Systems/oan-helm main (ci/deploy/release_images.py). The stage does not wait for
            // the merge and ends green once the pull request is open; a person with write access merges it and oan-helm's
            // release workflow then publishes the chart and updates CHANGELOG.md. If the pull request cannot be opened the
            // stage is UNSTABLE and says why. One pull request per commit merged to develop: a re-run of a commit that
            // oan-helm main already carries opens nothing, and neither does the merge of a chart-pin pull request.
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { env.DELIVERY_ACTION == 'deploy' } }
            }
            agent { label 'vpn-agent2' }
            options { timeout(time: 15, unit: 'MINUTES') }
            steps {
                checkout scm
                sh 'mkdir -p service-outcomes && rm -f service-outcomes/registry-images.tsv service-outcomes/oan-helm-pr.txt'
                unstash 'image-digests'
                script {
                    def subject = sh(returnStdout: true, script: 'git log -1 --pretty=%s').trim()
                    catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                        withCredentials([usernamePassword(credentialsId: "${OAN_HELM_FORK_CRED_ID}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                            withEnv(["COMMIT_SUBJECT=${subject}"]) {
                                sh 'python3 ci/deploy/release_images.py'
                            }
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
            archiveArtifacts artifacts: 'ci-output/native-worker-save/**', allowEmptyArchive: true
        }
    }
}

}
return this
