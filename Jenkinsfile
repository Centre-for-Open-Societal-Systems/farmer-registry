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
    stages {
        stage('Checkout and validate') {
            steps {
                checkout scm
                script {
                    // checkout scm does not always export GIT_COMMIT globally.
                    // Resolve the actual workspace revision before tagging images.
                    def commit = sh(returnStdout: true, script: 'git rev-parse --verify HEAD').trim()
                    if (!(commit ==~ /[0-9a-f]{40}/)) {
                        error('Could not resolve the checked-out Git commit')
                    }
                    env.IMAGE_TAG = commit.take(12)
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
                        for component in staff-api partner-api celery db-seed sanity-tests staff-ui; do
                          image="$ECR_REGISTRY/$ECR_PATH/$component:$IMAGE_TAG"
                          docker tag "coss-ci/$component:$IMAGE_TAG" "$image"
                          docker push "$image"
                        done
                    '''
                }
                stash name: 'dev-deployment', includes: 'helm/**,ci/**', excludes: 'helm/**/charts/**,helm/**/Chart.lock'
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
                        sh '''
                            set -eu
                            docker build -t "coss-ci/validation:$IMAGE_TAG" ci/jenkins
                            bash ci/jenkins/deploy-dev.sh
                        '''
                    }
                }
            }
        }
    }
}
