pipeline {
    agent any

    parameters {
     
        booleanParam(name: 'DEPLOY_TO_FAR', defaultValue: false,
            description: 'Also run the Deploy stage against the far namespace. Leave OFF until a first deploy through this pipeline has been done deliberately and reviewed.')
    }

    environment {
        AWS_ACCOUNT_ID = "${env.AWS_ACCOUNT_ID}"
        AWS_REGION     = "ap-south-1"
        ECR_REGISTRY   = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
        ECR_PATH       = "openg2p/farmer-registry"

     
        RP_VERSION     = "0.0.0-develop.384"

        // No STAFF_UI_VERSION here: the staff-ui target in the root Dockerfile owns
        // that pin, so CI builds the base image the developers build against.

        // No DASHBOARD_URL: nothing serves the dashboard in this deployment, so the
        // staff UI is built without its Dashboard header button (staff-ui passes an
        // empty DASHBOARD_URL below). Set one again once dashboard-ui is deployed.

        NEXT_PUBLIC_PORTAL_URL = "http://portal.localtest.me:3000"

        HELM_RELEASE   = "farmer-registry"
        HELM_NAMESPACE = "far"
        HELM_CHART_DIR = "helm/openg2p-farmer-registry"
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('ECR Login') {
            steps {
                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-ecr-creds']]) {
                    sh "aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}"
                }
            }
        }

        stage('Build & Push') {
            steps {
                script {
                    env.IMAGE_TAG = env.GIT_COMMIT.take(12)

                    // Build the root Dockerfile's targets, the same definition docker
                    // compose builds, so CI ships what the developers run. The
                    // per-component docker/*/Dockerfile copies had drifted from it:
                    // staff-ui was still on the 1.1.1 base without the intake photo
                    // widget styles, and staff-api, partner-api and celery lacked
                    // docker/patches/patch_platform.py. sanity-tests has no root target.
                    def components = [
                        [name: 'staff-api',     dockerfile: 'Dockerfile', target: 'staff-api',   args: "--build-arg RP_VERSION=${RP_VERSION}"],
                        [name: 'staff-ui',      dockerfile: 'Dockerfile', target: 'staff-ui',    args: "--build-arg DASHBOARD_URL="],
                        [name: 'partner-api',   dockerfile: 'Dockerfile', target: 'partner-api', args: "--build-arg RP_VERSION=${RP_VERSION}"],
                        [name: 'celery',        dockerfile: 'Dockerfile', target: 'celery',      args: "--build-arg RP_VERSION=${RP_VERSION}"],
                        [name: 'db-seed',       dockerfile: 'Dockerfile', target: 'db-seed',     args: "--build-arg RP_VERSION=${RP_VERSION}"],
                        [name: 'sanity-tests',  dockerfile: 'docker/sanity-tests/Dockerfile',    args: "--build-arg RP_VERSION=${RP_VERSION}"],
                        // dashboard-ui is skipped until dashboard-ui/lib/ is committed -- it
                        // cannot build from a clean checkout without it. The Helm chart does
                        // not deploy this image, so nothing downstream depends on it yet.
                        // [name: 'dashboard-ui',  dockerfile: 'docker/dashboard-ui/Dockerfile',  args: "--build-arg NEXT_PUBLIC_PORTAL_URL=${NEXT_PUBLIC_PORTAL_URL}"],
                    ]

                    components.each { c ->
                        def image  = "${ECR_REGISTRY}/${ECR_PATH}/${c.name}:${env.IMAGE_TAG}"
                        def latest = "${ECR_REGISTRY}/${ECR_PATH}/${c.name}:develop"
                        def target = c.target ? "--target ${c.target}" : ''
                        sh """
                            docker build ${c.args} ${target} \
                                -f ${c.dockerfile} -t ${image} -t ${latest} .
                            docker push ${image}
                            docker push ${latest}
                        """
                    }
                }
            }
        }

        stage('Stash chart') {
            // Deploy runs on a different (vpn-agent2) node -- carry just the
            // local chart directory over, not the whole repo/build context.
            steps {
                stash name: 'farmer-chart', includes: "${HELM_CHART_DIR}/**"
            }
        }

        stage('Deploy to Staging (far namespace)') {
            // beforeAgent: decide before asking for vpn-agent2. Without it every build
            // waits for that node first, and one with DEPLOY_TO_FAR off queues
            // forever while it is offline instead of skipping this stage.
            when {
                beforeAgent true
                allOf {
                    branch 'develop'
                    expression { return params.DEPLOY_TO_FAR }
                }
            }
         
            agent { label 'vpn-agent2' }
            steps {
                unstash 'farmer-chart'
                withCredentials([file(credentialsId: 'staging-farmer-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh """
                     
                        helm repo add openg2p-gitlab https://gitlab.com/api/v4/projects/84460547/packages/helm/stable || true
                        helm repo update openg2p-gitlab
                        helm dependency build ${HELM_CHART_DIR}

                        cat > /tmp/values-far-cicd-\${BUILD_NUMBER}.yaml <<EOF
registry:
  staffApi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/staff-api
      tag: "${env.IMAGE_TAG}"
  staffUi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/staff-ui
      tag: "${env.IMAGE_TAG}"
  partnerApi:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/partner-api
      tag: "${env.IMAGE_TAG}"
  celeryWorker:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/celery
      tag: "${env.IMAGE_TAG}"
  celeryBeat:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/celery
      tag: "${env.IMAGE_TAG}"
  dbSeed:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/db-seed
      tag: "${env.IMAGE_TAG}"
  sanity:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/sanity-tests
      tag: "${env.IMAGE_TAG}"
# Registry only. The chart's analytics layer -- the bulk sample-data generator,
# reporting views and their hourly refresh, the Superset dashboard import and
# the Insights maps content -- is left out of this deploy.
analytics:
  bulkSample:
    enabled: false
  reportingViews:
    enabled: false
  dashboards:
    enabled: false
mapsContent:
  enabled: false
EOF

                        # Keep the release's own values (hostnames, Keycloak and IAM
                        # wiring, cookie domain) and change only what this build owns.
                        # The chart defaults render placeholder *.openg2p.org hosts, so
                        # upgrading from the CI file alone would reset the live
                        # environment to them. Only a missing release (a first install)
                        # may go ahead without values; any other read failure stops here.
                        if ! helm get values ${HELM_RELEASE} -n ${HELM_NAMESPACE} -o yaml > /tmp/far-values-current-\${BUILD_NUMBER}.yaml 2> /tmp/far-values-current-\${BUILD_NUMBER}.err; then
                            grep -q 'release: not found' /tmp/far-values-current-\${BUILD_NUMBER}.err || { cat /tmp/far-values-current-\${BUILD_NUMBER}.err; exit 1; }
                            echo "No ${HELM_RELEASE} release in ${HELM_NAMESPACE} yet -- installing with the chart defaults."
                            : > /tmp/far-values-current-\${BUILD_NUMBER}.yaml
                        fi

                        # Dry-run render of exactly what the upgrade below applies.
                        helm template ${HELM_RELEASE} ${HELM_CHART_DIR} -n ${HELM_NAMESPACE} \
                            -f /tmp/far-values-current-\${BUILD_NUMBER}.yaml \
                            -f /tmp/values-far-cicd-\${BUILD_NUMBER}.yaml > /tmp/far-new-\${BUILD_NUMBER}.yaml
                        echo "Rendered \$(wc -l < /tmp/far-new-\${BUILD_NUMBER}.yaml) lines to /tmp/far-new-\${BUILD_NUMBER}.yaml"

                        helm upgrade --install ${HELM_RELEASE} ${HELM_CHART_DIR} -n ${HELM_NAMESPACE} \
                            -f /tmp/far-values-current-\${BUILD_NUMBER}.yaml \
                            -f /tmp/values-far-cicd-\${BUILD_NUMBER}.yaml --timeout 20m

                       
                        kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-api -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-ui -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-partner-api -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-celery-worker -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-celery-beat-producer -n ${HELM_NAMESPACE} --timeout=180s

                        
                        # explicit log of that outcome
                        echo "=== db-seed Job outcome ==="
                        kubectl get job ${HELM_RELEASE}-db-seed -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
                        echo "=== sanity Job outcome ==="
                        kubectl get job ${HELM_RELEASE}-sanity -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
                    """
                }
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f || true'
            sh "docker logout ${ECR_REGISTRY} || true"
        }
    }
}