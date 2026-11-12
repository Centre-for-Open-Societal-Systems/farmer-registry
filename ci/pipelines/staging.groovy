// A merge into staging promotes the chart develop built from this source tree: the same image digests, under an rc
// version, deployed with the staging values. Nothing is built, and the build fails if develop never built this tree.
// fresh-install and deploy are operator actions (ci/pipelines/operator.groovy) that need protected rehearsal evidence.
def call() {
    pipeline {
        agent any
        options { skipDefaultCheckout(true); disableConcurrentBuilds(); retry(count: 2, conditions: [agent(), nonresumable()]); timestamps(); timeout(time: 60, unit: 'MINUTES') }
        parameters {
            booleanParam(name: 'LOAD_SAMPLE_DATA', defaultValue: false,
                description: 'Load the sample records (db-seed hook) during this staging deploy. Leave off for a clean registry.')
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
                        env.EFFECTIVE_ACTION = env.DELIVERY_ACTION ?: 'promote'
                        if (env.EFFECTIVE_ACTION == 'validate-only') {
                            currentBuild.description = 'VALIDATION ONLY - staging was not deployed'
                            echo 'No cluster action (operator action validate-only): this successful build validates source only.'
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
            stage('Promote and deploy') {
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION == 'promote' } }
                agent { label 'oan-ci-deploy' }
                steps {
                    checkout scm
                    withCredentials([
                        file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG'),
                        [$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds'],
                        usernamePassword(credentialsId: 'oan-helm-fork-token', usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')
                    ]) {
                        sh 'bash ci/deploy/promote-staging.sh'
                    }
                    script { currentBuild.description = 'Promoted to staging in namespace farmer' }
                    // The loader never fails the upgrade (it always exits 0), so its SUMMARY line is printed here, and
                    // the build is UNSTABLE when not every sample farmer is in the register.
                    // The script does nothing unless LOAD_SAMPLE_DATA is on.
                    catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE', catchInterruptions: false) {
                        withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                            sh 'bash ci/deploy/sample-data-summary.sh'
                        }
                    }
                    // The connector release follows oan-helm's staging values on every promotion, as crop and livestock
                    // upgrade theirs: the services deploy below is an operator action, so without this a values change
                    // (the qa move) never reached the running connector. --atomic: a failed upgrade restores it and
                    // fails the build. Runs before the definitions, which call the connector's admin API.
                    withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                        sh 'bash ci/deploy/connector-staging.sh'
                    }
                    // The connector definitions declared in git (helm/environments/staging/farmer-connector-definitions.yaml),
                    // applied on every promotion as crop and livestock apply theirs: the services deploy below is an
                    // operator action, so without this a merge into staging never creates or updates them.
                    catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE', catchInterruptions: false) {
                        withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                            sh 'bash ci/deploy/connector-definitions.sh staging'
                        }
                    }
                }
            }
            stage('Deploy (registry)') {
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION in ['deploy', 'fresh-install'] } }
                agent { label 'oan-ci-deploy' }
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
                when { expression { env.EFFECTIVE_ACTION == 'deploy' && env.COORDINATE_SERVICES == 'true' } }
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
                    stash name: 'staging-services', includes: 'helm/**,ci/**,scripts/**,integrations/**,docker/registry-connector-ui/**,service-outcomes/staging-build.json', excludes: 'helm/**/charts/**', useDefaultExcludes: false
                }
            }
            stage('Deploy (services)') {
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION == 'deploy' && env.COORDINATE_SERVICES == 'true' } }
                agent { label 'oan-ci-deploy' }
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
                        // The connector definitions declared in git (helm/environments/staging/farmer-connector-definitions.yaml).
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                            withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                                sh 'bash ci/deploy/connector-definitions.sh staging'
                            }
                        }
                        archiveArtifacts artifacts: 'service-outcomes/*.json', allowEmptyArchive: true
                    }
                }
            }
            stage('Deliver dashboard') {
                // The farmer dashboard UI from oan-helm main: chart repository/farmer-registry-dashboard-*.tgz and values
                // environments/staging/values/farmer-dashboard.yaml, through oan-helm's scripts/ci/deliver_staging_dashboards.sh
                // (helm upgrade --install --reset-values --atomic). Git is the only source of its host and Gateway. A failure
                // marks the build unstable: the registry is already delivered, and --atomic restores the dashboard.
                when { beforeAgent true; expression { env.EFFECTIVE_ACTION == 'promote' } }
                agent { label 'oan-ci-deploy' }
                steps {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE', catchInterruptions: false) {
                        withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                            sh '''
                              set -eu
                              dir=.oan-helm-dashboard
                              rm -rf "$dir"
                              git clone --quiet --depth 1 --filter=blob:none --sparse \\
                                https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git "$dir"
                              git -C "$dir" sparse-checkout set --no-cone /scripts/ci/ /environments/staging/values/ \\
                                '/repository/farmer-registry-dashboard-*.tgz'
                              echo "oan-helm main $(git -C "$dir" rev-parse --short=12 HEAD)"
                              if grep -q '^ *farmer)' "$dir/scripts/ci/deliver_staging_dashboards.sh"; then
                                bash "$dir/scripts/ci/deliver_staging_dashboards.sh" farmer
                              else
                                echo "oan-helm main cannot deliver one dashboard yet; skipped"
                              fi
                              rm -rf "$dir"
                            '''
                        }
                    }
                }
            }
        }
        post {
            always { archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true }
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
                        body: "Farmer Registry staging build or deploy failed.\n\nJob:     ${env.JOB_NAME}\nBranch:  ${env.BRANCH_NAME}\nBuild:   #${env.BUILD_NUMBER}\nURL:     ${env.BUILD_URL}\nConsole: ${env.BUILD_URL}console\n\nJenkins"
                    )
                } catch (err) {
                    echo "notification not sent: ${err.message}"
                }
            }
        }
        }
    }
}
return this
