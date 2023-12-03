# Pulumi AWS Infrastructure Deployment

This repository provides a Pulumi project for deploying infrastructure on AWS across different environments (`dev` and `demo`).

## Prerequisites
- Ensure that the [AWS CLI](https://aws.amazon.com/cli/) is installed and configured with both `dev` and `demo` profiles.
- Install the [Pulumi CLI](https://www.pulumi.com/docs/get-started/aws/install-pulumi/).

## Initialization

For first-time setup:

### Set AWS profile
```bash
aws configure --profile demo
aws configure --profile dev
export AWS_PROFILE=demo
export AWS_PROFILE=dev
aws configure list


```

### Initialize the Pulumi project

```bash
pulumi new aws-python
```

### Create environments for dev and demo
```bash
pulumi stack init dev
pulumi stack init demo
```

### Configure the dev environment
```bash
pulumi stack select dev
pulumi config set aws:profile dev
```

### Configure the demo environment
```bash
pulumi stack select demo
pulumi config set aws:profile demo
```

### Define the CIDR block
```bash
pulumi config set cidrBlock "10.0.0.0/16"
pulumi config set customAmiId "ami-020b251b4f78f405a"
```

### Deploy to the dev environment

```bash
pulumi stack select dev
AWS_PROFILE=dev pulumi up
```

### Deploy to the demo environment
```bash
pulumi stack select demo
AWS_PROFILE=demo pulumi up
```

### Check and Set the AWS region configured
```bash
pulumi config get aws:region
pulumi config set aws:region us-west-1
```

### Destroy resources in the dev environment
```bash
pulumi stack select dev
pulumi destroy
```

### Destroy resources in the demo environment
```bash
pulumi stack select demo
pulumi destroy
```

pulumi stack -> will give the stack selected


If you change the region destroy the stack using the below command
```bash
pulumi stack rm --force demo  
```

This will delete or create the resource which had problem in getting created or deleting the resource

```bash
pulumi refresh 
```

pulumi up

pulumi down

Set the Secret in Pulumi Configuration: You can use the Pulumi CLI to set the secret:

```bash
pulumi config set db_name "csye6225"
pulumi config set username "csye6225"
pulumi config set --secret dbPassword YOUR_PASSWORD_HERE
pulumi config set hosted-zone-id "Z0498823D9PQ1YWPC88E"
pulumi config set domain-name "dev.prakruthi.me"
pulumi config set --secret mail_gun_api_key "5e04305e95f9391296d9594211a436f3-30b58138-688005de"
pulumi config set mail_gun_domain prakruthi.me


```
# Copy the installed packages from the virtual environment to the package directory
cp -r venv/lib/python3.11/site-packages/* .  # replace python3.x with your Python version
