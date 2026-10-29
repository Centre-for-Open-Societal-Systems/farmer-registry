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
    }
    parameters {
        choice(name: 'DELIVERY_ACTION', choices: ['publish-only', 'deploy', 'fresh-install'],
            description: 'publish-only builds and pushes the images. deploy upgrades the existing dev release with them. fresh-install backs up the dev registry databases, uninstalls the release, drops the databases and installs the pinned chart again on an empty database (all dev farmer data is lost; Commons is untouched).')
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
                    // Branch-index builds may not yet have the new parameters.
                    // Resolve that case to publication, never cluster mutation.
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
                        docker run --rm --network none --user "$(id -u):$(id -g)" \
                          -e DELIVERY_ACTION \
                          -e ECR_REGISTRY -e IMAGE_TAG -e SOURCE_COMMIT \
                          -v "$PWD:/repo" "coss-ci/validation:$IMAGE_TAG" \
                          python ci/delivery.py publication service-outcomes/publication.json
                    '''
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
