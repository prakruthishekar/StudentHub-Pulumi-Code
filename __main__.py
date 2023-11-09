import pulumi
from pulumi_aws import ec2
from pulumi_aws import get_availability_zones
from pulumi_aws import rds
from pulumi_aws import route53
from pulumi_aws import ec2, get_availability_zones, rds, route53, iam

config = pulumi.Config()
db_name = config.require("db_name")
db_username = config.require("username")

vpc = ec2.Vpc('vpc',
    cidr_block= config.require("cidrBlock"),
    tags={'Name': 'my-vpc'})

pulumi.export('vpc_id', vpc.id)

# Retrieve the configurations
base_cidr_block = config.require("cidrBlock")

# Base CIDR block
base_first_octet, base_second_octet = base_cidr_block.split('.')[0:2]

# Get the availability zones for the region
availability_zones_result = get_availability_zones()
availability_zones = pulumi.Output.from_input(availability_zones_result.names).apply(lambda az: az[0:3])

# Create subnets
public_subnets = availability_zones.apply(
    lambda azs: [
        ec2.Subnet(f'public-subnet-{az}',
            vpc_id=vpc.id,
            cidr_block=f"{base_first_octet}.{base_second_octet}.{index + 1}.0/24",
            availability_zone=az,
            map_public_ip_on_launch=True, # makes this a public subnet
            tags={"Name": f'public-subnet-{az}'}
        ) for index, az in enumerate(azs)
    ]
)

private_subnets = availability_zones.apply(
    lambda azs: [
        ec2.Subnet(f'private-subnet-{az}',
            vpc_id=vpc.id,
            cidr_block=f"{base_first_octet}.{base_second_octet}.{index + 11}.0/24",
            availability_zone=az,
            tags={"Name": f'private-subnet-{az}'}
        ) for index, az in enumerate(azs)
    ]
)

pulumi.export("Private Subnets", private_subnets)
# Log Subnets
# public_subnets.apply(lambda subnets: [print(f"Public Subnet Created: {subnet.id}") for subnet in subnets if subnet is not None])
# private_subnets.apply(lambda subnets: [print(f"Private Subnet Created: {subnet.id}") for subnet in subnets if subnet is not None])

# Create an Internet Gateway and attach the Internet Gateway to the VPC.
internet_gateway = ec2.InternetGateway("my-internet-gateway",
    vpc_id=vpc.id
)

pulumi.export("Internet Gateway ID", internet_gateway.id)

# Create a public route table
public_route_table = ec2.RouteTable("public-route-table",
    vpc_id=vpc.id
)

pulumi.export("Public route table", public_route_table.id)

# Attach all public subnets to the public route table
public_subnets.apply(
    lambda subnets: [
        ec2.RouteTableAssociation(f"public-subnet-rt-association-{index}",
            subnet_id=subnet.id,
            route_table_id=public_route_table.id
        ) for index, subnet in enumerate(subnets)
    ]
)

# Create a private route table
private_route_table = ec2.RouteTable("private-route-table",
    vpc_id=vpc.id
)

# Attach all private subnets to the private route table
private_subnets.apply(
    lambda subnets: [
        ec2.RouteTableAssociation(f"private-subnet-rt-association-{index}",
            subnet_id=subnet.id,
            route_table_id=private_route_table.id
        ) for index, subnet in enumerate(subnets)
    ]
)

# Create a public route in the public route table
internet_gateway_route = ec2.Route("internet-gateway-route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=internet_gateway.id
)


# 1. Create the Application Security Group
app_security_group = ec2.SecurityGroup('app-security-group',
    vpc_id=vpc.id,
    description='EC2 Security Group for web applications',
    ingress=[
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=22,
            to_port=22,
            cidr_blocks=['0.0.0.0/0']
        ),
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=80,
            to_port=80,
            cidr_blocks=['0.0.0.0/0']
        ),
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=8080,
            to_port=8080,
            cidr_blocks=['0.0.0.0/0']
        ),
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=443,
            to_port=443,
            cidr_blocks=['0.0.0.0/0']
        ),
        # Add additional ingress rules for other ports as necessary
    ],
    # Add an egress rule to allow outbound traffic to the RDS instance
    egress= [
        ec2.SecurityGroupEgressArgs(
            protocol="tcp",
            from_port=443,
            to_port=443,
            cidr_blocks=['0.0.0.0/0'],
            description="Allow outbound HTTPS traffic for CloudWatch Logs"
        ),
        # Allow other necessary outbound traffic, e.g., to RDS instance
        ec2.SecurityGroupEgressArgs(
            protocol="tcp",
            from_port=3306,
            to_port=3306,
            cidr_blocks=['0.0.0.0/0'],
            description="Allow outbound MySQL traffic to RDS instance"
        ),
        # Default rule to allow all outbound traffic
        # Remove if you want to restrict outbound traffic
        ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic by default"
        ),
    ],
        tags={"Name": "app-security-group"}
)


# Create DB Security Group
db_security_group = ec2.SecurityGroup('db-security-group',
    vpc_id=vpc.id,
    description='Security Group for RDS instances',
    ingress=[
        ec2.SecurityGroupIngressArgs(
            protocol='tcp',
            from_port=3306,  # For MySQL/MariaDB
            to_port=3306,
            security_groups=[app_security_group.id]  # Reference to the application security group
        )
    ],
    egress=[
        ec2.SecurityGroupEgressArgs(
            protocol="tcp",
            from_port=443,
            to_port=443,
            cidr_blocks=['0.0.0.0/0'],
            description="Allow outbound HTTPS traffic for CloudWatch Logs"
        )
    ]
)

# Create RDS Parameter Group for MySQL
rds_parameter_group = rds.ParameterGroup("db-parameter-group",
    family="mariadb10.6",
    description="Database parameter group for Mariadb",
    parameters=[
        rds.ParameterGroupParameterArgs(
            name="character_set_server",
            value="utf8mb4"  # Set the character set to utf8mb4 which supports a wide range of characters including emojis
        ),
        rds.ParameterGroupParameterArgs(
            name="character_set_client",
            value="utf8mb4"
        ),
        rds.ParameterGroupParameterArgs(
            name="collation_server",
            value="utf8mb4_unicode_ci"  # Set the collation for utf8mb4
        ),
        rds.ParameterGroupParameterArgs(
            name="max_connections",
            value="100"  # Limit the maximum number of connections
        ),
        rds.ParameterGroupParameterArgs(
            name="slow_query_log",
            value="1"  # Enable the slow query log
        ),
        rds.ParameterGroupParameterArgs(
            name="long_query_time",
            value="2"  # Log queries that take more than 2 seconds
        ),
        # Add more parameters as necessary
    ]
)

# Create a DB subnet group
db_subnet_group = rds.SubnetGroup('db-subnet-group',
                                  subnet_ids=private_subnets,
                                  description='My DB subnet group',
                                  tags={"Name": "db-subnet-group"})

# Export the DB subnet group name
pulumi.export('db_subnet_group_name', db_subnet_group.name)

# Create RDS Instance
rds_instance = rds.Instance("db-instance",
    engine="mariadb",  # Choose your DB engine: 'mysql', 'mariadb', 'postgres', etc.
    instance_class="db.t2.micro",
    allocated_storage=20,
    db_name=db_name,
    username=db_username,
    password=config.require_secret("dbPassword"),  #  keeping secrets like passwords in Pulumi config
    parameter_group_name=rds_parameter_group.name,
    skip_final_snapshot=True,
    vpc_security_group_ids=[db_security_group.id],
    db_subnet_group_name=db_subnet_group.name,  # Choose the appropriate subnet group
    multi_az=False,
    publicly_accessible=False
)

# Export the name of DB Instance
pulumi.export('db_endpoint', rds_instance.id)


# Create the EC2 instance
ami_id = config.require("customAmiId")  # Ensure you set this value in your Pulumi configuration


#User data generation
user_data=pulumi.Output.all(rds_instance.endpoint, db_username, config.require_secret("dbPassword")).apply(
    lambda args: f"""#!/bin/bash
    # Create necessary directories and files with proper permissions
    sudo mkdir -p /opt/webapp
    sudo touch /opt/webapp/user-data-success.log
    sudo chown -R $(whoami): /opt/webapp
    
    # Write environment variables to the .env file
    echo 'DB_HOST={args[0]}' | sudo tee /opt/webapp/.env
    echo 'DB_NAME={args[1]}' | sudo tee -a /opt/webapp/.env
    echo 'DB_PASSWORD={args[2]}' | sudo tee -a /opt/webapp/.env
    echo 'DB_USERNAME={args[1]}' | sudo tee -a /opt/webapp/.env
    
    # Record successful execution
    echo 'Script executed successfully' | sudo tee /opt/webapp/user-data-success.log
    
    # Export environment variables to the system environment
    echo 'DB_HOST={args[0]}' | sudo tee -a /etc/environment
    echo 'DB_PORT=3306' | sudo tee -a /etc/environment
    echo 'DB_NAME={args[1]}' | sudo tee -a /etc/environment
    echo 'DB_USERNAME={args[1]}' | sudo tee -a /etc/environment
    echo 'DB_PASSWORD={args[2]}' | sudo tee -a /etc/environment

    # Start the CloudWatch agent
    sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \\
    -a fetch-config \\
    -m ec2 \\
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/CloudWatchAgent.json \\
    -s
    """
)


# Create IAM Role for EC2 instance
ec2_role = iam.Role("ec2-role",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "sts:AssumeRole",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Effect": "Allow",
                "Sid": ""
            }
        ]
    }"""
)

# # Define the custom CloudWatch Logs policy
# policy_json = """{
#     "Version": "2012-10-17",
#     "Statement": [{
#         "Effect": "Allow",
#         "Action": [
#             "logs:CreateLogGroup",
#             "logs:CreateLogStream",
#             "logs:PutLogEvents"
#         ],
#         "Resource": "*"
#     }]
# }"""

# # Create an inline policy and attach it to the IAM role
# cloudwatch_logs_policy = iam.RolePolicy("cloudwatch-logs-policy",
#     role=ec2_role.name,
#     policy=policy_json
# )

# Attach the CloudWatch Agent policy to the IAM role
cloudwatch_policy_attachment = iam.RolePolicyAttachment("cloudwatch-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
    role=ec2_role.name
)

# Create an instance profile for the EC2 instance
ec2_instance_profile = iam.InstanceProfile('my_instance_profile',
   role=ec2_role.name, # Assign the IAM role to the instance profile
)

# EC2 Instance
ec2_instance = ec2.Instance('my-ec2-instance',
    instance_type='t2.micro',
    ami=ami_id,
    iam_instance_profile=ec2_instance_profile.name, # Assign the instance profile to the EC2 instance
    vpc_security_group_ids=[app_security_group.id],
    subnet_id=public_subnets[0].id,
    key_name='webapp',
    ebs_block_devices=[
        ec2.InstanceEbsBlockDeviceArgs(
            device_name='/dev/xvda',
            volume_type='gp2',
            volume_size=25,
            delete_on_termination=True
        )
    ],
    instance_initiated_shutdown_behavior="stop",
    root_block_device= ec2.InstanceRootBlockDeviceArgs(
        volume_size=25,
        volume_type='gp2',
    ),
    disable_api_termination=False,
    tags={
        'Name': 'my-ec2-instance'
    },
    user_data=user_data,
    opts=pulumi.ResourceOptions(depends_on=[rds_instance])
)

pulumi.export('ec2_instance_id', ec2_instance.id)

hosted_zone_id = config.require("hosted-zone-id")
domain_name = config.require("domain-name")

# Reference to your EC2 instance resource
dns_record = route53.Record("dnsRecord",
    zone_id=hosted_zone_id,
    name=domain_name,
    type="A",
    ttl=300,
    records=[ec2_instance.public_ip]
)

# Output the DNS record value
pulumi.export('dnsRecord', dns_record.fqdn)
