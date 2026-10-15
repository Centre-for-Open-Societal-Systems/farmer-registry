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
                script { env.IMAGE_TAG = env.GIT_COMMIT.take(12) }
                sh '''
                    set -eu
                    python3 -m venv .ci-venv
                    .ci-venv/bin/pip install --quiet -r ci/jenkins/requirements.txt
                    .ci-venv/bin/python -m pytest -q test/test_rp_pin_lockstep.py \
                      test/test_jenkins_deployment.py test/test_pm_manifest.py \
                      test/test_odk_location_media.py test/test_odk_geo_compatibility.py \
                      test/test_shared_geo_migration.py farmer-extension/tests/test_metadata_effective_layer.py
                    .ci-venv/bin/python odk/test_transform.py > .ci-odk-transform.log
                    bash -n ci/jenkins/deploy-dev.sh
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
                            python3 -m venv .ci-venv
                            .ci-venv/bin/pip install --quiet PyYAML==6.0.2
                            export PATH="$PWD/.ci-venv/bin:$PATH"
                            bash ci/jenkins/deploy-dev.sh
                        '''
                    }
                }
            }
        }
    }
}
