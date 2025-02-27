#!/bin/bash
# Requirements: docker.io and docker-compose on the server, firewall-closed port 5000 to public
# Local user has to be in docker group, docker-compose-v2 package installed

# Arm can be (slowly) crosscompiled on x86 processors using https://www.stereolabs.com/docs/docker/building-arm-container-on-x86/
# You probably need to run this before building the image:
# sudo apt-get install qemu binfmt-support qemu-user-static # Install the qemu packages
# docker run --rm --privileged multiarch/qemu-user-static --reset -p yes # This step will execute the registering scripts
# docker run --platform=linux/arm64/v8 --rm -t arm64v8/ubuntu uname -m # Testing the emulation environment

# Stop on any error
set -e
# Automatically export all variables
set -a

# Load and export configuration
source deploy.env

# Setup remote Docker context
CONTEXT_NAME="copytrader-remote"
echo "Setting up Docker context..."
docker context create ${CONTEXT_NAME} --docker "host=ssh://${REMOTE_USER}@${REMOTE_HOST}" 2>/dev/null || true

# Set up registry if not running
# docker --context ${CONTEXT_NAME} run -d \
#   -p 5000:5000 \
#   --name registry \
#   -v /opt/docker-registry:/var/lib/registry \
#   registry:2 2>/dev/null || echo "Registry is already running"

export REGISTRY=""
# export REGISTRY="localhost:5000/"
# export DOCKER_OPTS="--insecure-registry $REGISTRY"

if [ "$1" = "-b" ]; then
    shift # rotate $2 to $1 etc

    echo "Building image locally and pushing to registry"
    # docker-compose build
    docker build -f Dockerfile --platform=$ARCH -t leftys/copytrader --progress=plain .
    # docker buildx build --output type=registry,name=${REGISTRY}bazos-app,push=true,compression=zstd,compression-level=10 .

    echo "Preparing remote directory and opening registry ssh forward..."
    ssh ${REMOTE_USER}@${REMOTE_HOST} -L 5000:localhost:5000 "mkdir -p ${REMOTE_WORK_DIR} && sleep 10" &
    sleep 1

    echo "Pushing image to registry..."
    docker push leftys/copytrader
    # docker push ${REGISTRY}bazos-app || \
    #     echo "{\"insecure-registries\": { \"hosts\": [\"${REGISTRY}\"] }}" | sudo tee -a "/etc/docker/daemon.json" 

    # echo "Pulling image from registry..."
    # REGISTRY="localhost:5000/" docker --context ${CONTEXT_NAME} pull localhost:5000/bazos-app
fi

# Deploy on remote
echo "Deploying on remote..."
docker --context ${CONTEXT_NAME} compose --project-name copytrader up -d --pull always $1

echo "Deployment complete!"