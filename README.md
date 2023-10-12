# Pulumi AWS Infrastructure Deployment

This repository provides a Pulumi project for deploying infrastructure on AWS across different environments (`dev` and `demo`).

## Prerequisites
- Ensure that the [AWS CLI](https://aws.amazon.com/cli/) is installed and configured with both `dev` and `demo` profiles.
- Install the [Pulumi CLI](https://www.pulumi.com/docs/get-started/aws/install-pulumi/).

## Initialization

For first-time setup:

### Initialize the Pulumi project

$ pulumi new aws-python

### Create environments for dev and demo
$ pulumi stack init dev
$ pulumi stack init demo

### Configure the dev environment
$ pulumi stack select dev
$ pulumi config set aws:profile dev

### Configure the demo environment
$ pulumi stack select demo
$ pulumi config set aws:profile demo

### Define the CIDR block
$ pulumi config set cidrBlock "10.0.0.0/16"

### Deploy to the dev environment
$ pulumi stack select dev
$ AWS_PROFILE=dev pulumi up

### Deploy to the demo environment
$ pulumi stack select demo
$ AWS_PROFILE=demo pulumi up

### Destroy resources in the dev environment
$ pulumi stack select dev
$ pulumi destroy

### Destroy resources in the demo environment
$ pulumi stack select demo
$ pulumi destroy