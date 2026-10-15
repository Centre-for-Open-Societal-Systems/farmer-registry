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
        ECR_PATH = 'openg2p/farmer-registry'
        HELM_RELEASE = 'farmer-registry'
        HELM_NAMESPACE = 'farmer'
    }
    parameters {
        booleanParam(name: 'COORDINATE_SERVICES', defaultValue: true,
            description: 'Build and independently upgrade available optional services; failures mark UNSTABLE.')
        booleanParam(name: 'APPLY_COMMONS_IDENTITY', defaultValue: false,
            description: 'Apply reviewed Commons staff identity values; requires fresh farmer-dev-identity-evidence credential.')
    }
    stages {
        stage('Checkout and validate') {
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
                }
                sh '''
                    set -eu
                    docker build -t "coss-ci/validation:$IMAGE_TAG" ci/jenkins
                    docker run --rm --user "$(id -u):$(id -g)" \
                      -v "$PWD:/repo:ro" "coss-ci/validation:$IMAGE_TAG" \
                      bash ci/jenkins/validate.sh
                '''
            }
        }
        stage('Build RC images') {
            steps {
                sh '''
                    set -eu
                    for component in staff-api partner-api celery db-seed sanity-tests staff-ui; do
                      docker build -f "docker/$component/Dockerfile" -t "coss-ci/$component:$IMAGE_TAG" .
                    done
                    docker run --rm -v "$PWD:/repo:ro" -w /repo/farmer-extension \
                      --entrypoint python "coss-ci/staff-api:$IMAGE_TAG" -m unittest \
                      tests.test_domain_validation_utils tests.test_farmer_geo_sync \
                      tests.test_intake_record_image_urls tests.test_household_family_size
                '''
            }
        }
        stage('Publish dev images') {
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
                          image="$ECR_REGISTRY/$ECR_PATH/$component:$IMAGE_TAG"
                          docker tag "coss-ci/$component:$IMAGE_TAG" "$image"
                          docker push "$image"
                          digest=$(aws ecr describe-images --region "$AWS_REGION" \
                            --repository-name "$ECR_PATH/$component" --image-ids "imageTag=$IMAGE_TAG" \
                            --query 'imageDetails[0].imageDigest' --output text)
                          printf '%s\t%s\t%s\n' "$component" "$image" "$digest" >> service-outcomes/registry-images.tsv
                        done
                    '''
                }
            }
        }
        stage('Prepare dev deployment') {
            when { allOf { branch 'develop'; not { changeRequest() } } }
            steps {
                stash name: 'dev-deployment', includes: 'helm/**,ci/**,service-outcomes/**', excludes: 'helm/**/charts/**,helm/**/Chart.lock'
            }
        }
        stage('Deploy new dev') {
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() } }
            }
            agent { label 'vpn-agent2' }
            steps {
                dir('dev-deployment') {
                    deleteDir()
                    unstash 'dev-deployment'
                    withCredentials([file(credentialsId: 'farmer-dev-kubeconfig', variable: 'KUBECONFIG')]) {
                        script {
                          def deployRegistry = {
                            sh '''
                            set -eu
                            export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/jenkins
                            bash ci/jenkins/deploy-dev.sh
                            '''
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
        stage('Build optional services') {
            when { allOf { branch 'develop'; not { changeRequest() }; expression { params.COORDINATE_SERVICES } } }
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
                stash name: 'optional-deployment', includes: 'ci/**,service-outcomes/build.json'
            }
        }
        stage('Deploy optional services') {
            when {
                beforeAgent true
                allOf { branch 'develop'; not { changeRequest() }; expression { params.COORDINATE_SERVICES } }
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
                          sh 'bash ci/connector/fetch-backup-container.sh'
                        }
                      }
                    }
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                        withCredentials([file(credentialsId: 'farmer-dev-kubeconfig', variable: 'KUBECONFIG')]) {
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
        }
    }
}
