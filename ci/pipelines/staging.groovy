// Staging remains on its verified legacy layout. No dev chart or connector cutover.
def call() {
    pipeline {
        agent any
        options { skipDefaultCheckout(true); disableConcurrentBuilds(); timestamps(); timeout(time: 60, unit: 'MINUTES') }
        parameters {
            booleanParam(name: 'DEPLOY_STAGING', defaultValue: false,
                description: 'Opt in only after reviewing legacy layout compatibility; leaves the staging connector unchanged.')
        }
        environment {
            AWS_REGION = 'ap-south-1'
            ECR_PATH = 'openg2p/farmer-registry'
            HELM_RELEASE = 'farmer-registry'
            HELM_NAMESPACE = 'far'
            HELM_CHART_DIR = 'helm/openg2p-farmer-registry'
            RP_VERSION = '0.0.0-develop.384'
        }
        stages {
            stage('Validate staging prerequisites') {
                steps {
                    checkout scm
                    script {
                        if (env.BRANCH_NAME != 'staging' || env.CHANGE_ID) { error('Staging delivery requires the staging branch') }
                        env.SOURCE_COMMIT = sh(returnStdout: true, script: 'git rev-parse --verify HEAD').trim()
                        if (!(env.SOURCE_COMMIT ==~ /[0-9a-f]{40}/)) { error('Invalid source commit') }
                        env.IMAGE_TAG = env.SOURCE_COMMIT.take(12)
                        if (params.DEPLOY_STAGING) {
                            if (!fileExists('Dockerfile')) { error('Legacy staging Dockerfile missing; platform migration requires a separate review') }
                            def metadata = readFile('helm/openg2p-farmer-registry/Chart.yaml')
                            if (!metadata.contains('0.0.0-develop.384')) { error('Staging chart/platform compatibility has not been verified') }
                        }
                    }
                    sh 'docker build -t "coss-ci/validation:$IMAGE_TAG" ci/validation'
                    sh 'docker run --rm -v "$PWD:/repo:ro" "coss-ci/validation:$IMAGE_TAG" python ci/environments.py staging'
                }
            }
            stage('Build and publish staging Registry') {
                when { expression { params.DEPLOY_STAGING } }
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
                        sh 'bash ci/build/staging-legacy.sh'
                    }
                    stash name: 'staging-deployment', includes: 'helm/**,ci/**,service-outcomes/**', excludes: 'helm/**/charts/**', useDefaultExcludes: false
                }
            }
            stage('Deploy staging Registry (far)') {
                when { beforeAgent true; expression { params.DEPLOY_STAGING } }
                agent { label 'vpn-agent2' }
                steps {
                    dir('staging-deployment') {
                        deleteDir()
                        unstash 'staging-deployment'
                        withCredentials([file(credentialsId: 'staging-farmer-kubeconfig', variable: 'KUBECONFIG')]) {
                            sh 'bash ci/deploy/staging-legacy.sh'
                        }
                    }
                }
            }
        }
        post { always { archiveArtifacts artifacts: 'service-outcomes/*.json,service-outcomes/*.tsv', allowEmptyArchive: true } }
    }
}
return this
