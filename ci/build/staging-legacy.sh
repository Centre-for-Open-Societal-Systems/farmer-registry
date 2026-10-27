#!/usr/bin/env bash
set -euo pipefail
set +x
: "${ECR_REGISTRY:?Missing ECR registry}"
: "${IMAGE_TAG:?Missing source commit tag}"
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf "$DOCKER_CONFIG"' EXIT
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
mkdir -p service-outcomes
: > service-outcomes/staging-registry-images.tsv
for component in staff-api staff-ui partner-api celery db-seed sanity-tests; do
    image="$ECR_REGISTRY/$ECR_PATH/$component:$IMAGE_TAG"
    if [[ "$component" == sanity-tests ]]; then
        docker build --build-arg "RP_VERSION=$RP_VERSION" -f docker/sanity-tests/Dockerfile -t "$image" .
    else
        docker build -f "docker/oan/$component.Dockerfile" -t "$image" .
    fi
    docker push "$image"
    digest=$(aws ecr describe-images --region "$AWS_REGION" --repository-name "$ECR_PATH/$component" --image-ids "imageTag=$IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text)
    printf '%s\t%s\t%s\n' "$component" "$image" "$digest" >> service-outcomes/staging-registry-images.tsv
done
