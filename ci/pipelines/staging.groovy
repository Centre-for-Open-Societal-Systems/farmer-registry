// Merging staging only validates. Promotion needs protected rehearsal evidence.
def call() {
    pipeline {
        agent any
        options { skipDefaultCheckout(true); disableConcurrentBuilds(); timestamps(); timeout(time: 60, unit: 'MINUTES') }
        parameters {
            choice(name: 'DELIVERY_ACTION', choices: ['validate-only', 'fresh-install', 'deploy'],
                description: 'validate-only checks the source and changes nothing. fresh-install backs up the staging registry databases to the protected backup target, removes the OAN release in namespace farmer if present, drops its databases and installs the pinned OAN chart on empty databases. deploy upgrades the existing OAN release. Either cluster action also needs DEPLOY_STAGING. The legacy far release is never touched.')
            booleanParam(name: 'DEPLOY_STAGING', defaultValue: false,
                description: 'Second guard: nothing reaches the staging cluster unless this is set together with a DELIVERY_ACTION other than validate-only.')
            booleanParam(name: 'COORDINATE_SERVICES', defaultValue: false,
                description: 'Release available staging dashboards and prepare the paused promoted connector.')
        }
        environment {
            DELIVERY_ENVIRONMENT = 'staging'
            AWS_REGION = 'ap-south-1'
            HELM_RELEASE = 'farmer-registry'
            HELM_NAMESPACE = 'farmer'
            KUBECONFIG_CREDENTIAL = 'staging-farmer-kubeconfig'
        }
        stages {
            stage('Test') {
                steps {
                    checkout scm
                    dir('service-outcomes') { deleteDir() }
                    script {
                        if (env.BRANCH_NAME != 'staging' || env.CHANGE_ID) { error('Staging delivery requires the staging branch') }
                        env.SOURCE_COMMIT = sh(returnStdout: true, script: 'git rev-parse --verify HEAD').trim()
                        if (!(env.SOURCE_COMMIT ==~ /[0-9a-f]{40}/)) { error('Invalid source commit') }
                        env.IMAGE_TAG = env.SOURCE_COMMIT.take(12)
                        // Both guards must agree before any cluster action; otherwise this build only validates.
                        env.EFFECTIVE_ACTION = params.DEPLOY_STAGING ? params.DELIVERY_ACTION : 'validate-only'
                        if (env.EFFECTIVE_ACTION == 'validate-only') {
                            currentBuild.description = 'VALIDATION ONLY - staging was not deployed'
                            echo 'No cluster action (DEPLOY_STAGING=false or DELIVERY_ACTION=validate-only): this successful build validates source only.'
                        } else {
                            currentBuild.description = 'Staging ' + env.EFFECTIVE_ACTION + ' requested - acceptance pending'
                        }
                    }
                    sh '''
                      set -eu
                      docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                      docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" \
                        "coss-ci/validation:$IMAGE_TAG" bash ci/validation/validate.sh
                    '''
                    stash name: 'staging-deployment', includes: 'helm/**,ci/**,scripts/**,integrations/**,docker/**,farmer-extension/**,test/runtime/**', excludes: 'helm/**/charts/**,**/__pycache__/**', useDefaultExcludes: false
                }
            }
            stage('Deploy (registry)') {
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION in ['deploy', 'fresh-install'] } }
                agent { label 'vpn-agent2' }
                steps {
                    dir('staging-deployment') {
                        deleteDir()
                        unstash 'staging-deployment'
                        withCredentials([
                            file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG'),
                            file(credentialsId: 'staging-farmer-rehearsal', variable: 'STAGING_EVIDENCE_FILE')
                        ]) {
                            script {
                                def runRegistry = { String entry ->
                                    withEnv(['DELIVERY_ACTION=' + env.EFFECTIVE_ACTION, 'DELIVERY_ENTRY=' + entry]) {
                                        sh '''
                                          set -eu
                                          set +x
                                          mkdir -p service-outcomes
                                          docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation
                                          export ECR_REGISTRY=recorded-in-protected-evidence
                                          export REGISTRY_OUTCOME_FILE="$PWD/service-outcomes/registry.json"
                                          bash "$DELIVERY_ENTRY"
                                        '''
                                    }
                                }
                                try {
                                    // A first-install evidence record (New Dev was the rehearsal, the target is empty) never
                                    // archives anything, so the backup credentials are not bound for it: a credential id that
                                    // does not exist would fail withCredentials. The script validates the record and re-checks
                                    // the cluster; if a release or database exists it refuses, and any other evidence needs the
                                    // credentials (the script refuses without them).
                                    def firstInstall = env.EFFECTIVE_ACTION == 'fresh-install' && sh(returnStatus: true,
                                        script: 'set +x; grep -Eq \'"mode"[[:space:]]*:[[:space:]]*"first-install"\' "$STAGING_EVIDENCE_FILE"') == 0
                                    if (firstInstall) {
                                        echo 'First-install evidence: backup credentials are not bound (nothing exists to archive).'
                                        runRegistry('ci/deploy/fresh-install-staging.sh')
                                    } else if (env.EFFECTIVE_ACTION == 'fresh-install') {
                                        // The pg_dump archive target. Both credentials are created by the Jenkins admin:
                                        // an SSH key, and a file holding user@host, the directory and the host key.
                                        withCredentials([
                                            sshUserPrivateKey(credentialsId: 'staging-farmer-backup-ssh', keyFileVariable: 'BACKUP_SSH_KEY'),
                                            file(credentialsId: 'staging-farmer-backup-target', variable: 'BACKUP_TARGET_FILE')
                                        ]) { runRegistry('ci/deploy/fresh-install-staging.sh') }
                                    } else {
                                        runRegistry('ci/deploy/deploy-rc.sh')
                                    }
                                } finally {
                                    archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true
                                }
                            }
                        }
                        script { currentBuild.description = 'Registry ' + env.EFFECTIVE_ACTION + ' done in namespace farmer - signed intake acceptance remains a separate gate' }
                    }
                }
            }
            stage('Build (services)') {
                when { expression { env.EFFECTIVE_ACTION == 'deploy' && params.COORDINATE_SERVICES } }
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
            stage('Deploy (services)') {
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION == 'deploy' && params.COORDINATE_SERVICES } }
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
                                file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG'),
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
