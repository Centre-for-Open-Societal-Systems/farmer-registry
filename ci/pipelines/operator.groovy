// Operator pipeline: the actions that destroy data, change a release outside the merge path, or need a person to choose.
// Job setup (done once by ASMIT, who is the only person who runs this job): a multibranch job whose Script Path is
// "Jenkinsfile.operator", with automatic branch and webhook triggering suppressed. Every build asks for approval by
// 'admin' before anything runs. Merges to develop and staging never reach this file: ci/pipelines/dev.groovy and
// ci/pipelines/staging.groovy have no parameters and run the default path on their own.
def call() {
    properties([parameters([
        choice(name: 'OPERATOR_ACTION', choices: ['fresh-install', 'deploy-with-commons-identity', 'deploy-without-services', 'validate-only', 'deploy-with-services'],
            description: 'develop: fresh-install (backs up the dev registry databases, uninstalls the release, DROPS the databases and installs the pinned chart on an empty database), deploy-with-commons-identity (the normal deploy plus the reviewed Commons staff identity values; needs the farmer-dev-identity-evidence credential), deploy-without-services (the normal deploy without the optional services). staging: fresh-install (backs up, removes the OAN release, DROPS its databases, installs the pinned chart), validate-only (checks the source, changes nothing), deploy-with-services (upgrades the existing OAN release and coordinates the staging services).')
    ])])
    if (env.CHANGE_ID || !(env.BRANCH_NAME in ['develop', 'staging'])) {
        error('The operator pipeline runs only on develop or staging, never for a pull request')
    }
    if (!params.OPERATOR_ACTION) {
        currentBuild.result = 'NOT_BUILT'
        echo 'Parameters are registered now. Start the build again with Build with Parameters.'
        return
    }
    if (!currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')) {
        currentBuild.result = 'NOT_BUILT'
        echo 'Operator actions run only when a person starts them, never from branch indexing or a webhook.'
        return
    }
    def allowed = env.BRANCH_NAME == 'staging' ? ['fresh-install', 'validate-only', 'deploy-with-services'] : ['fresh-install', 'deploy-with-commons-identity', 'deploy-without-services']
    if (!(params.OPERATOR_ACTION in allowed)) {
        error("${params.OPERATOR_ACTION} is not an action for ${env.BRANCH_NAME}; choose one of ${allowed}")
    }

    // Only ASMIT runs this job: the approval is restricted to the Jenkins 'admin' user.
    input message: "Run '${params.OPERATOR_ACTION}' on ${env.BRANCH_NAME}? fresh-install DROPS the registry databases.", ok: 'Run', submitter: 'admin'
    switch (params.OPERATOR_ACTION) {
        case 'fresh-install': env.DELIVERY_ACTION = 'fresh-install'; break
        case 'validate-only': env.DELIVERY_ACTION = 'validate-only'; break
        case 'deploy-with-commons-identity': env.DELIVERY_ACTION = 'deploy'; env.APPLY_COMMONS_IDENTITY = 'true'; break
        case 'deploy-without-services': env.DELIVERY_ACTION = 'deploy'; env.COORDINATE_SERVICES = 'false'; break
        case 'deploy-with-services': env.DELIVERY_ACTION = 'deploy'; env.COORDINATE_SERVICES = 'true'; break
    }
    def delivery
    node {
        checkout scm
        def environment = env.BRANCH_NAME == 'staging' ? 'staging' : 'dev'
        delivery = load("ci/pipelines/${environment}.groovy")
    }
    currentBuild.description = "Operator action: ${params.OPERATOR_ACTION}"
    delivery.call()
}
return this
