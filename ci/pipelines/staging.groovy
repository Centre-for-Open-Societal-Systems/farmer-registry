// Merging staging only validates. Promotion needs protected rehearsal evidence.
def call() {
    pipeline {
        agent any
        options { skipDefaultCheckout(true); disableConcurrentBuilds(); timestamps(); timeout(time: 60, unit: 'MINUTES') }
        parameters {
            booleanParam(name: 'DEPLOY_STAGING', defaultValue: false,
                description: 'Promote tested RC images after Farmer maintenance and verified final backups.')
            booleanParam(name: 'COORDINATE_SERVICES', defaultValue: false,
                description: 'Release available staging dashboards and prepare the paused promoted connector.')
        }
        environment {
            DELIVERY_ENVIRONMENT = 'staging'
            AWS_REGION = 'ap-south-1'
            HELM_RELEASE = 'farmer-registry'
            HELM_NAMESPACE = 'far'
            KUBECONFIG_CREDENTIAL = 'staging-farmer-kubeconfig'
        }
        stages {
            stage('Validate staging RC') {
                steps {
                    checkout scm
                    dir('service-outcomes') { deleteDir() }
                    script {
                        if (env.BRANCH_NAME != 'staging' || env.CHANGE_ID) { error('Staging delivery requires the staging branch') }
                        env.SOURCE_COMMIT = sh(returnStdout: true, script: 'git rev-parse --verify HEAD').trim()
                        if (!(env.SOURCE_COMMIT ==~ /[0-9a-f]{40}/)) { error('Invalid source commit') }
                        env.IMAGE_TAG = env.SOURCE_COMMIT.take(12)
                    }
                    sh '''
                      set -eu
                      docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                      docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" \
                        "coss-ci/validation:$IMAGE_TAG" bash ci/validation/validate.sh
                    '''
                    stash name: 'staging-deployment', includes: 'helm/**,ci/**,scripts/**,integrations/**,docker/**,farmer-extension/**,tests/runtime/**', excludes: 'helm/**/charts/**,**/__pycache__/**', useDefaultExcludes: false
                }
            }
            stage('Promote rehearsed staging Registry (far)') {
                when { beforeAgent true; expression { params.DEPLOY_STAGING } }
                agent { label 'vpn-agent2' }
                steps {
                    dir('staging-deployment') {
                        deleteDir()
                        unstash 'staging-deployment'
                        withCredentials([
                            file(credentialsId: 'staging-farmer-kubeconfig', variable: 'KUBECONFIG'),
                            file(credentialsId: 'staging-farmer-rehearsal', variable: 'STAGING_EVIDENCE_FILE')
                        ]) {
                            sh '''
                              set -eu
                              set +x
                              mkdir -p service-outcomes
                              docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                              export ECR_REGISTRY=recorded-in-protected-evidence
                              export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                              bash ci/deploy/deploy-rc.sh
                            '''
                        }
                        archiveArtifacts artifacts: 'service-outcomes/*.json', allowEmptyArchive: true
                    }
                }
            }
            stage('Build staging optional services') {
                when { expression { params.DEPLOY_STAGING && params.COORDINATE_SERVICES } }
                steps {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                        withCredentials([
                            file(credentialsId: 'staging-farmer-dev-services', variable: 'DEV_MANIFEST'),
                            file(credentialsId: 'staging-farmer-dev-acceptance', variable: 'DEV_ACCEPTANCE'),
                            [$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds']
                        ]) {
                            script {
                                env.ECR_REGISTRY = sh(returnStdout: true, script: '''
                                  set +x
                                  account=$(aws sts get-caller-identity --query Account --output text)
                                  case "$account" in *[!0-9]*|'') exit 1 ;; esac
                                  test "${#account}" = 12
                                  printf '%s.dkr.ecr.%s.amazonaws.com' "$account" "$AWS_REGION"
                                ''').trim()
                            }
                            sh 'bash ci/services/run-container.sh build --environment staging --registry "$ECR_REGISTRY" --input "$DEV_MANIFEST" --acceptance "$DEV_ACCEPTANCE" --output service-outcomes/staging-build.json'
                        }
                    }
                    stash name: 'staging-services', includes: 'helm/**,ci/**,scripts/**,integrations/**,service-outcomes/staging-build.json', excludes: 'helm/**/charts/**', useDefaultExcludes: false
                }
            }
            stage('Deploy staging optional services') {
                when { beforeAgent true; expression { params.DEPLOY_STAGING && params.COORDINATE_SERVICES } }
                agent { label 'vpn-agent2' }
                steps {
                    dir('staging-services') {
                        deleteDir()
                        unstash 'staging-services'
                        script {
                            env.CONNECTOR_BACKUP_DIRECTORY = ''
                            catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                                withCredentials([string(credentialsId: 'staging-farmer-connector-backup-directory', variable: 'STAGING_SNAPSHOT_DIRECTORY')]) {
                                    env.CONNECTOR_BACKUP_DIRECTORY = env.STAGING_SNAPSHOT_DIRECTORY
                                }
                            }
                        }
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                            withCredentials([
                                file(credentialsId: 'staging-farmer-kubeconfig', variable: 'KUBECONFIG'),
                                file(credentialsId: 'staging-farmer-dev-acceptance', variable: 'DEV_ACCEPTANCE')
                            ]) {
                                // Missing protected connector backup fails that service;
                                // dashboards still run independently. Scheduling stays off.
                                sh 'bash ci/services/run-container.sh deploy --environment staging --registry "$ECR_REGISTRY" --input service-outcomes/staging-build.json --acceptance "$DEV_ACCEPTANCE" --output service-outcomes/staging-deploy.json'
                            }
                        }
                        archiveArtifacts artifacts: 'service-outcomes/*.json', allowEmptyArchive: true
                    }
                }
            }
        }
        post { always { archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true } }
    }
}
return this
