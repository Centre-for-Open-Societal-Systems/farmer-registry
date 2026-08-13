pipeline {
    agent any

    environment {
        AWS_REGION   = 'ap-south-1'
        ECR_BASE     = 'oan/farmer-registry'
        RP_VERSION   = '0.0.0-develop.383'
        NAMESPACE    = 'dev'
        RELEASE_NAME = 'farmer-registry'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Build Images') {
            steps {
                withCredentials([string(credentialsId: 'AWS_ACCOUNT_ID', variable: 'AWS_ACCOUNT_ID')]) {
                    sh '''
                        ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
                        BRANCH="${GIT_BRANCH##*/}"
                        TAG="${BRANCH}-${BUILD_NUMBER}"

                        echo "=== Building images for branch: ${BRANCH} tag: ${TAG} ==="

                        # staff-api
                        docker build \
                            --build-arg RP_VERSION=${RP_VERSION} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/staff-api:${TAG} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/staff-api:${BRANCH} \
                            --file docker/staff-api/Dockerfile \
                            --no-cache .

                        # celery
                        docker build \
                            --build-arg RP_VERSION=${RP_VERSION} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/celery:${TAG} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/celery:${BRANCH} \
                            --file docker/celery/Dockerfile \
                            --no-cache .

                        # db-seed
                        docker build \
                            --build-arg RP_VERSION=${RP_VERSION} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/db-seed:${TAG} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/db-seed:${BRANCH} \
                            --file docker/db-seed/Dockerfile \
                            --no-cache .

                        # partner-api
                        docker build \
                            --build-arg RP_VERSION=${RP_VERSION} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/partner-api:${TAG} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/partner-api:${BRANCH} \
                            --file docker/partner-api/Dockerfile \
                            --no-cache .

                        # sanity-tests
                        docker build \
                            --build-arg RP_VERSION=${RP_VERSION} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/sanity-tests:${TAG} \
                            --tag ${ECR_REGISTRY}/${ECR_BASE}/sanity-tests:${BRANCH} \
                            --file docker/sanity-tests/Dockerfile \
                            --no-cache .

                        echo "=== All images built ==="
                    '''
                }
            }
        }

        stage('Push to ECR') {
            steps {
                withCredentials([string(credentialsId: 'AWS_ACCOUNT_ID', variable: 'AWS_ACCOUNT_ID')]) {
                    sh '''
                        ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
                        BRANCH="${GIT_BRANCH##*/}"
                        TAG="${BRANCH}-${BUILD_NUMBER}"

                        echo "=== Logging in to ECR ==="
                        aws ecr get-login-password --region ${AWS_REGION} | \
                            docker login --username AWS --password-stdin ${ECR_REGISTRY}

                        echo "=== Pushing images ==="
                        for SVC in staff-api celery db-seed partner-api sanity-tests; do
                            docker push ${ECR_REGISTRY}/${ECR_BASE}/${SVC}:${TAG}
                            docker push ${ECR_REGISTRY}/${ECR_BASE}/${SVC}:${BRANCH}
                            echo "Pushed ${SVC}:${TAG}"
                        done

                        echo "=== Cleanup local images ==="
                        for SVC in staff-api celery db-seed partner-api sanity-tests; do
                            docker rmi ${ECR_REGISTRY}/${ECR_BASE}/${SVC}:${TAG} || true
                            docker rmi ${ECR_REGISTRY}/${ECR_BASE}/${SVC}:${BRANCH} || true
                        done
                        docker system prune -f || true

                        echo "=== All images pushed ==="
                    '''
                }
            }
        }

        stage('Deploy to Dev') {
            when { branch 'develop' }
            agent { label 'vpn-deploy-agent' }
            steps {
                withCredentials([
                    string(credentialsId: 'AWS_ACCOUNT_ID', variable: 'AWS_ACCOUNT_ID'),
                    file(credentialsId: 'gen2-kubeconfig', variable: 'KUBECONFIG')
                ]) {
                    sh '''
                        ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
                        BRANCH="${GIT_BRANCH##*/}"
                        TAG="${BRANCH}-${BUILD_NUMBER}"

                        echo "=== Deploying to dev namespace ==="

                        helm repo add openg2p-gitlab \
                            https://gitlab.com/api/v4/projects/84460547/packages/helm/stable || true
                        helm dependency build ./helm/openg2p-farmer-registry

                        helm upgrade --install ${RELEASE_NAME} ./helm/openg2p-farmer-registry \
                            --namespace gen2 \
                            --create-namespace \
                            --timeout 10m \
                            --set registry.staffApi.image.repository=${ECR_REGISTRY}/${ECR_BASE}/staff-api \
                            --set registry.staffApi.image.tag=${TAG} \
                            --set registry.partnerApi.image.repository=${ECR_REGISTRY}/${ECR_BASE}/partner-api \
                            --set registry.partnerApi.image.tag=${TAG} \
                            --set registry.celeryWorker.image.repository=${ECR_REGISTRY}/${ECR_BASE}/celery \
                            --set registry.celeryWorker.image.tag=${TAG} \
                            --set registry.celeryBeat.image.repository=${ECR_REGISTRY}/${ECR_BASE}/celery \
                            --set registry.celeryBeat.image.tag=${TAG} \
                            --set registry.dbSeed.image.repository=${ECR_REGISTRY}/${ECR_BASE}/db-seed \
                            --set registry.dbSeed.image.tag=${TAG} \
                            --set sanity.image.repository=${ECR_REGISTRY}/${ECR_BASE}/sanity-tests \
                            --set sanity.image.tag=${TAG}

                        echo "=== Waiting for rollout ==="
                        kubectl rollout status deployment/${RELEASE_NAME}-staff-api \
                            -n gen2 --timeout=120s || true

                        echo "=== Deployment status ==="
                        kubectl get pods -n gen2 | grep ${RELEASE_NAME}
                    '''
                }
            }
        }

        stage('Deploy to Staging') {
            when { branch 'main' }
            steps {
                withCredentials([
                    string(credentialsId: 'AWS_ACCOUNT_ID', variable: 'AWS_ACCOUNT_ID'),
                    file(credentialsId: 'dev-kubeconfig', variable: 'KUBECONFIG')
                ]) {
                    input message: "Approve deployment of farmer-registry:${GIT_BRANCH##*/}-${BUILD_NUMBER} to staging?"
                    sh '''
                        ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
                        BRANCH="${GIT_BRANCH##*/}"
                        TAG="${BRANCH}-${BUILD_NUMBER}"

                        echo "=== Deploying to staging namespace ==="

                        helm repo add openg2p-gitlab \
                            https://gitlab.com/api/v4/projects/84460547/packages/helm/stable || true
                        helm dependency build ./helm/openg2p-farmer-registry

                        helm upgrade --install ${RELEASE_NAME}-staging ./helm/openg2p-farmer-registry \
                            --namespace ${NAMESPACE} \
                            --timeout 10m \
                            --set registry.staffApi.image.repository=${ECR_REGISTRY}/${ECR_BASE}/staff-api \
                            --set registry.staffApi.image.tag=${TAG} \
                            --set registry.partnerApi.image.repository=${ECR_REGISTRY}/${ECR_BASE}/partner-api \
                            --set registry.partnerApi.image.tag=${TAG} \
                            --set registry.celeryWorker.image.repository=${ECR_REGISTRY}/${ECR_BASE}/celery \
                            --set registry.celeryWorker.image.tag=${TAG} \
                            --set registry.celeryBeat.image.repository=${ECR_REGISTRY}/${ECR_BASE}/celery \
                            --set registry.celeryBeat.image.tag=${TAG} \
                            --set registry.dbSeed.image.repository=${ECR_REGISTRY}/${ECR_BASE}/db-seed \
                            --set registry.dbSeed.image.tag=${TAG} \
                            --set sanity.image.repository=${ECR_REGISTRY}/${ECR_BASE}/sanity-tests \
                            --set sanity.image.tag=${TAG}

                        echo "=== Waiting for rollout ==="
                        kubectl rollout status deployment/${RELEASE_NAME}-staging-staff-api \
                            -n ${NAMESPACE} --timeout=120s || true

                        echo "=== Deployment status ==="
                        kubectl get pods -n ${NAMESPACE} | grep ${RELEASE_NAME}-staging
                    '''
                }
            }
        }
    }

    post {
        success {
            script {
                def committerEmail = sh(
                    script: "git log -1 --pretty=format:'%ae'",
                    returnStdout: true
                ).trim()
                def committerName = sh(
                    script: "git log -1 --pretty=format:'%an'",
                    returnStdout: true
                ).trim()
                if (committerEmail.contains('noreply')) {
                    committerEmail = 'devops@yourorg.com'
                }
                mail(
                    to: committerEmail,
                    subject: "✅ Build SUCCESS: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                    body: """
Hi ${committerName},

Farmer Registry build and deployment succeeded!

Job:    ${env.JOB_NAME}
Branch: ${env.GIT_BRANCH}
Build:  #${env.BUILD_NUMBER}
URL:    ${env.BUILD_URL}

Regards,
Jenkins
                    """
                )
            }
        }
        failure {
            script {
                def committerEmail = sh(
                    script: "git log -1 --pretty=format:'%ae'",
                    returnStdout: true
                ).trim()
                def committerName = sh(
                    script: "git log -1 --pretty=format:'%an'",
                    returnStdout: true
                ).trim()
                if (committerEmail.contains('noreply')) {
                    committerEmail = 'devops@yourorg.com'
                }
                mail(
                    to: committerEmail,
                    subject: "❌ Build FAILED: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                    body: """
Hi ${committerName},

Farmer Registry build or deployment failed.

Job:    ${env.JOB_NAME}
Branch: ${env.GIT_BRANCH}
Build:  #${env.BUILD_NUMBER}
URL:    ${env.BUILD_URL}

Regards,
Jenkins
                    """
                )
            }
        }
    }
}