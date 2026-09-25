pipeline {
    agent any

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

        // farmer-registry-dashboard-api lives in its own (public) repository and is
        // built here beside the registry images. Each branch builds the
        // dashboard-api branch of the same name -- develop from develop, staging
        // from staging -- and falls back to develop where there is none. Set
        // DASHBOARD_API_REF on the job (a branch or tag) to pin one instead.
        // See docs/deployment.md §3.5.
        DASHBOARD_API_REPO = "https://github.com/Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api.git"

        HELM_RELEASE   = "farmer-registry"
        HELM_NAMESPACE = "far"
        HELM_CHART_DIR = "helm/openg2p-farmer-registry"
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Checkout dashboard-api') {
            steps {
                script {
                    // A PR build (BRANCH_NAME PR-<n>) matches on its source branch.
                    def ref = env.DASHBOARD_API_REF
                    if (!ref) {
                        def wanted = env.CHANGE_BRANCH ?: env.BRANCH_NAME
                        def found = wanted && sh(returnStatus: true,
                            script: "git ls-remote --exit-code --heads ${DASHBOARD_API_REPO} 'refs/heads/${wanted}' > /dev/null") == 0
                        ref = found ? wanted : 'develop'
                    }
                    // .build/ is ignored by git and by the root .dockerignore, so the
                    // clone never enters the registry images' build context.
                    sh "rm -rf .build/dashboard-api && git clone --quiet --depth 1 --branch '${ref}' ${DASHBOARD_API_REPO} .build/dashboard-api"
                    // Fail here, naming the cause, rather than as a bare "open Dockerfile"
                    // in Build & Push -- e.g. a branch the service has not reached yet.
                    if (!fileExists('.build/dashboard-api/Dockerfile')) {
                        error("dashboard-api ${ref} has no Dockerfile: merge the service into that branch of ${DASHBOARD_API_REPO}, or set DASHBOARD_API_REF")
                    }
                    env.DASHBOARD_API_REF_USED = ref
                    env.DASHBOARD_API_SHA = sh(returnStdout: true, script: 'git -C .build/dashboard-api rev-parse --short=12 HEAD').trim()
                    echo "dashboard-api: ${ref} @ ${env.DASHBOARD_API_SHA}"
                }
            }
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
                        // Built from its own repository, cloned by 'Checkout dashboard-api'.
                        [name: 'dashboard-api', dockerfile: '.build/dashboard-api/Dockerfile', context: '.build/dashboard-api',
                         args: "--label org.opencontainers.image.source=${DASHBOARD_API_REPO} --label org.opencontainers.image.revision=${env.DASHBOARD_API_SHA} --label org.opencontainers.image.ref.name=${env.DASHBOARD_API_REF_USED}"],
                    ]

                    components.each { c ->
                        def image  = "${ECR_REGISTRY}/${ECR_PATH}/${c.name}:${env.IMAGE_TAG}"
                        def latest = "${ECR_REGISTRY}/${ECR_PATH}/${c.name}:develop"
                        def target = c.target ? "--target ${c.target}" : ''
                        def context = c.context ?: '.'
                        sh """
                            docker build ${c.args} ${target} \
                                -f ${c.dockerfile} -t ${image} -t ${latest} ${context}
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

        stage('Deploy (far namespace)') {
            // Every develop build deploys to dev, and every staging build to staging;
            // other branches only build and push. Each credential is a kubeconfig for
            // the far:farmer-ci service account on that cluster:
            //   develop  gen2-dev-kubeconfig        dev, 10.0.1.166; its rights in far
            //                                       come from ci/k8s/farmer-deploy-rbac.yaml
            //   staging  staging-farmer-kubeconfig  staging, 10.0.1.212
            // beforeAgent: decide before asking for vpn-agent2, so a build of any other
            // branch never waits for that node.
            when {
                beforeAgent true
                anyOf {
                    branch 'develop'
                    branch 'staging'
                }
            }
         
            agent { label 'vpn-agent2' }
            environment {
                KUBECONFIG_CREDENTIAL = "${env.BRANCH_NAME == 'staging' ? 'staging-farmer-kubeconfig' : 'gen2-dev-kubeconfig'}"
            }
            steps {
                unstash 'farmer-chart'
                withCredentials([file(credentialsId: env.KUBECONFIG_CREDENTIAL, variable: 'KUBECONFIG')]) {
                    sh """
                     
                        helm repo add openg2p-gitlab https://gitlab.com/api/v4/projects/84460547/packages/helm/stable || true
                        helm repo update openg2p-gitlab
                        # `update`, not `build`: Chart.lock is gitignored (it pins a
                        # moving -develop tag, so it buys no determinism), which leaves
                        # the workspace copy on the agent as the only one -- and git
                        # never cleans an ignored file between builds. `build` trusts
                        # that stale lock and refuses the moment Chart.yaml's pin moves:
                        # "the lock file (Chart.lock) is out of sync with the
                        # dependencies file (Chart.yaml)", which is exactly what failed
                        # staging #4 on the .383 -> .384 bump. `update` re-resolves from
                        # Chart.yaml and rewrites the lock.
                        helm dependency update ${HELM_CHART_DIR}

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
    loadAttributes: false
  sanity:
    image:
      repository: ${ECR_REGISTRY}/${ECR_PATH}/sanity-tests
      tag: "${env.IMAGE_TAG}"
# The dashboard service for the OAN dashboards (ClusterIP only).
dashboardApi:
  enabled: true
  image:
    repository: ${ECR_REGISTRY}/${ECR_PATH}/dashboard-api
    tag: "${env.IMAGE_TAG}"
# Of the chart's analytics layer only the reporting views and their hourly
# refresh are deployed: the dashboard API reads fr_rpt_farmer and fr_rpt_land.
# The bulk sample-data generator, the Superset dashboard import and the Insights
# maps content stay out of this deploy.
analytics:
  bulkSample:
    enabled: false
  reportingViews:
    enabled: true
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

                        # The hook Jobs (db-seed, iam-register, sanity, reporting views) delete their pod
                        # when they give up, and its log goes with it: all helm reports
                        # is BackoffLimitExceeded. Copy their logs while helm runs, and
                        # print them if it fails.
                        LOGDIR=\$(mktemp -d)
                        ( set +x
                          while sleep 5; do
                            for P in \$(kubectl get pods -n ${HELM_NAMESPACE} -o name | grep -E '/${HELM_RELEASE}-(db-seed|iam-register|sanity|fr-reporting-views)-'); do
                              kubectl logs \$P -n ${HELM_NAMESPACE} --all-containers --tail=100 > \$LOGDIR/\${P#pod/}.log 2>&1 || true
                            done
                          done ) &
                        trap "set +e; kill \$! 2>/dev/null; wait \$! 2>/dev/null; rm -rf \$LOGDIR" EXIT

                        if ! helm upgrade --install ${HELM_RELEASE} ${HELM_CHART_DIR} -n ${HELM_NAMESPACE} \
                            -f /tmp/far-values-current-\${BUILD_NUMBER}.yaml \
                            -f /tmp/values-far-cicd-\${BUILD_NUMBER}.yaml --timeout 20m; then
                            for F in \$LOGDIR/*.log; do
                                [ -f \$F ] || continue
                                echo "=== \$(basename \$F .log): last 100 log lines ==="
                                cat \$F
                            done
                            exit 1
                        fi

                       
                        kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-api -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-staff-portal-ui -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-partner-api -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-celery-worker -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-celery-beat-producer -n ${HELM_NAMESPACE} --timeout=180s
                        kubectl rollout status deployment/${HELM_RELEASE}-dashboard-api -n ${HELM_NAMESPACE} --timeout=180s

                        
                        # explicit log of that outcome
                        echo "=== db-seed Job outcome ==="
                        kubectl get job ${HELM_RELEASE}-db-seed -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
                        echo "=== sanity Job outcome ==="
                        kubectl get job ${HELM_RELEASE}-sanity -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
                        echo "=== reporting-views Job outcome ==="
                        kubectl get job ${HELM_RELEASE}-fr-reporting-views -n ${HELM_NAMESPACE} -o jsonpath='{.status.succeeded} succeeded / {.status.failed} failed{"\\n"}' || echo "(job not found under this name -- check the actual name with: kubectl get jobs -n ${HELM_NAMESPACE})"
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