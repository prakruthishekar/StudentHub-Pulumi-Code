import base64
import pulumi
from pulumi_aws import ec2
from pulumi_aws import get_availability_zones
from pulumi_aws import rds
from pulumi_aws import route53
import pulumi_aws as aws
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


# Security Group for Load Balancer
lb_security_group = ec2.SecurityGroup('lbSecurityGroup',
    vpc_id=vpc.id,
    description='Load balancer security group',
    ingress=[
        {'protocol': 'tcp', 'from_port': 80, 'to_port': 80, 'cidr_blocks': ['0.0.0.0/0']},
        {'protocol': 'tcp', 'from_port': 443, 'to_port': 443, 'cidr_blocks': ['0.0.0.0/0']}
    ],
    egress=[
            aws.ec2.SecurityGroupEgressArgs(
                from_port=0,
                to_port=0,
                protocol='-1',
                cidr_blocks=['0.0.0.0/0']
            )
            ])


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
         # Allow HTTP from Load Balancer Security Group
        ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=80,
            to_port=80,
            security_groups=[lb_security_group.id]
        ),
        # Allow HTTPS from Load Balancer Security Group
        ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=443,
            to_port=443,
            security_groups=[lb_security_group.id]
        ),
         ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8080,
            to_port=8080,
            security_groups=[lb_security_group.id]
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

# Attach the CloudWatch Agent policy to the IAM role
cloudwatch_policy_attachment = iam.RolePolicyAttachment("cloudwatch-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
    role=ec2_role.name
)

# Create an instance profile for the EC2 instance
ec2_instance_profile = iam.InstanceProfile('my_instance_profile',
   role=ec2_role.name, # Assign the IAM role to the instance profile
)

# Encode the user data script in base64
encoded_user_data = user_data.apply(lambda data: base64.b64encode(data.encode()).decode())

launch_template = ec2.LaunchTemplate("my-launch-template",
    instance_type='t2.micro',
    image_id=ami_id,  # Specify the AMI ID here
    iam_instance_profile={
        "name": ec2_instance_profile.name
    }, 
    # vpc_security_group_ids=[app_security_group.id],
    key_name='webapp',
    instance_initiated_shutdown_behavior="stop",
    disable_api_termination=False,
    network_interfaces=[aws.ec2.LaunchTemplateNetworkInterfaceArgs(
        associate_public_ip_address="true",
        security_groups=[app_security_group.id, db_security_group.id],  # Move security group here
    )],
    tags={
        'Name': 'my-ec2-instance'
    },
    user_data=encoded_user_data,
    opts=pulumi.ResourceOptions(depends_on=[rds_instance])
)

# Extract subnet IDs from public_subnets
public_subnet_ids = public_subnets.apply(lambda subnets: [subnet.id for subnet in subnets])

# Auto Scaling Group
autoscaling_group = aws.autoscaling.Group('autoscalingGroup',
    min_size=1,
    max_size=3,
    desired_capacity=1,
    launch_template={
        'id': launch_template.id,
        'version': "$Latest"
    },
    vpc_zone_identifiers=public_subnet_ids,
    tags=[aws.autoscaling.GroupTagArgs(
            key='Name',
            value='my-autoscale-group',
            propagate_at_launch=True
            ),
          aws.autoscaling.GroupTagArgs(
            key='AutoScalingGroup',
            value='web-app',
            propagate_at_launch=True
            ) 
    ]
)

# Auto Scaling Policies
scale_up_policy = aws.autoscaling.Policy('scaleUp',
    scaling_adjustment=1,
    adjustment_type='ChangeInCapacity',
    cooldown=60,
    autoscaling_group_name=autoscaling_group.name)

scale_down_policy = aws.autoscaling.Policy('scaleDown',
    scaling_adjustment=-1,
    adjustment_type='ChangeInCapacity',
    cooldown=60,
    autoscaling_group_name=autoscaling_group.name)

# We extract the ARNs using the .arn attribute and use the result for the alarms.
scale_up_policy_arn = scale_up_policy.arn
scale_down_policy_arn = scale_down_policy.arn

# CloudWatch Alarms for Auto Scaling
scale_up_alarm = aws.cloudwatch.MetricAlarm('scaleUpAlarm',
    comparison_operator='GreaterThanThreshold',
    evaluation_periods=2,
    metric_name='CPUUtilization',
    namespace='AWS/EC2',
    period=300,
    statistic='Average',
    threshold=5,
    alarm_actions=[scale_up_policy_arn],
    dimensions={'AutoScalingGroupName': autoscaling_group.name})

scale_down_alarm = aws.cloudwatch.MetricAlarm('scaleDownAlarm',
    comparison_operator='LessThanThreshold',
    evaluation_periods=2,
    metric_name='CPUUtilization',
    namespace='AWS/EC2',
    period=300,
    statistic='Average',
    threshold=3,
    alarm_actions=[scale_down_policy_arn],
    dimensions={'AutoScalingGroupName': autoscaling_group.name})

pulumi.export('launch_template_id', launch_template.id)

hosted_zone_id = config.require("hosted-zone-id")
domain_name = config.require("domain-name")


# Application Load Balancer
app_lb = aws.lb.LoadBalancer('appLoadBalancer',
    internal=False,
    load_balancer_type="application",
    security_groups=[lb_security_group.id],
    subnets=public_subnet_ids,
    enable_deletion_protection=False
)

# Create a target group
target_group = aws.lb.TargetGroup("targetGroup",
    port=8080,  # Use your application port here
    protocol="HTTP",  # or "HTTPS" if you're using SSL/TLS
    vpc_id=vpc.id,  # Use the VPC ID here
    target_type="instance",
    health_check=aws.lb.TargetGroupHealthCheckArgs(
                enabled=True,
                path='/healthz',
                protocol='HTTP',
                port='8080',
                timeout=25
            ),

)

# Create a listener
listener = aws.lb.Listener("listener",
    load_balancer_arn=app_lb.arn,
    port=80,  # Use the same application port
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
                type="forward",
                target_group_arn=target_group.arn
            )],
)

# DNS Updates with Route53
dns_record = aws.route53.Record('dnsRecord',
    zone_id=hosted_zone_id,  # Your Route53 Zone ID
    name=domain_name,  # Update with your domain
    type='A',
    aliases=[
        {
            'name': app_lb.dns_name,
            'zone_id': app_lb.zone_id,
            'evaluate_target_health': True
        }
    ])