import pulumi
from pulumi_aws import ec2
from pulumi_aws import get_availability_zones

config = pulumi.Config()

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
print(availability_zones_result)

# Create a VPC
vpc = ec2.Vpc('my-vpc',
    cidr_block=base_cidr_block,
    tags={"Name": "my-vpc"}
)

pulumi.export("VPC ID", vpc.id)


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

# Log Subnets
public_subnets.apply(lambda subnets: [print(f"Public Subnet Created: {subnet.id}") for subnet in subnets])
private_subnets.apply(lambda subnets: [print(f"Private Subnet Created: {subnet.id}") for subnet in subnets])

# Create an Internet Gateway and attach the Internet Gateway to the VPC.
internet_gateway = ec2.InternetGateway("my-internet-gateway",
    vpc_id=vpc.id
)

pulumi.export("Internet Gateway ID", internet_gateway.id)

# Create a public route table
public_route_table = ec2.RouteTable("public-route-table",
    vpc_id=vpc.id
)

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
route = ec2.Route("public-route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=internet_gateway.id
)

