from pulumi_aws import ec2,get_availability_zones
import pulumi
#VPC stuff
config = pulumi.Config()
data = config.require_object("data")

zones = get_availability_zones()
pub_subnets = []
priv_subnets = []
priv_subnets_cidrs = ["172.16.0.0/20","172.16.16.0/20","172.16.32.0/20"]
pub_subnets_cidrs = ["172.16.48.0/20","172.16.64.0/20","172.16.80.0/20"]

#ssh key
keypair = ec2.KeyPair("keypair", public_key=data.get("public_key"))

#VPC
vpc = ec2.Vpc(resource_name="vpc", cidr_block="172.16.0.0/16",enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        'Name': 'vpc',
    },
)


igw = ec2.InternetGateway(
    resource_name='igw',
    vpc_id=vpc.id,
    tags={
        'Name': 'igw',
    },
)


igw_route_table = ec2.RouteTable(
    resource_name='rt-vpc',
    vpc_id=vpc.id,
    routes=[ec2.RouteTableRouteArgs(
        cidr_block='0.0.0.0/0',
        gateway_id=igw.id,
    )],
    tags={
        'Name': 'rt-vpc',
    },
)

index = 0
for zone in zones.names:
    #private
    pub_subnet = ec2.Subnet(
        resource_name=f'pub-subnet-{zone}',
        vpc_id=vpc.id,
        map_public_ip_on_launch=True,
        cidr_block=pub_subnets_cidrs[index],
        availability_zone=zone,
    tags={
        'Name': f'pub-subnet-{zone}',
    },
    )

    #public
    priv_subnet = ec2.Subnet(
        resource_name=f'priv-subnet-{zone}',
        vpc_id=vpc.id,
        map_public_ip_on_launch=False,
        cidr_block=priv_subnets_cidrs[index],
        availability_zone=zone,
    tags={
        'Name': f'priv-subnet-{zone}',
    },
    )
    ec2.RouteTableAssociation(
        resource_name=f'pub-rt-asso-{zone}',
        route_table_id=igw_route_table.id,
        subnet_id=pub_subnet.id,
    )

    eip = ec2.Eip(resource_name=f'eip-{zone}', vpc=True,
    tags={
        'Name': f'eip-{zone}',
    },    )

    nat_gw = ec2.NatGateway(resource_name=f'nat-gw-{zone}',subnet_id=pub_subnet.id,
                             allocation_id=eip.id,
                        tags={
        'Name': f'nat-gw-{zone}',
    },

                             )

    priv_rt = ec2.RouteTable(resource_name=f'rt-subnet-{zone}',
        vpc_id=vpc.id,
        routes=[
            ec2.RouteTableRouteArgs(
                cidr_block="0.0.0.0/0",
                nat_gateway_id=nat_gw.id,
            )
        ],
                        tags={
        'Name': f'rt-subnet-{zone}',
    },
        )

    ec2.RouteTableAssociation(
            resource_name=f'priv-rt-asso-{zone}',
            route_table_id=priv_rt.id,
            subnet_id=priv_subnet.id,
    )

    pub_subnets.append(pub_subnet.id)
    priv_subnets.append(priv_subnet.id)

    index+=1

#Security groups
#bastion
bastion_sg = ec2.SecurityGroup(
        resource_name='bastion-sg',
        vpc_id=vpc.id,
        description="Allow SSH traffic to Bastion",
        ingress=[
        {
            "protocol": "tcp",
            "from_port": 22,
            "to_port": 22,
            "cidr_blocks": ["0.0.0.0/0"],
        }
        ],
    egress=[
        {
            "protocol": "-1",
            "from_port": 0,
            "to_port": 0,
            "cidr_blocks": ["0.0.0.0/0"],
        }
    ],
        tags={
        'Name': f'bastion-sg',
    },
)

#bastion not asked but nice to have
ami = ec2.get_ami(
        most_recent="true",
        owners=["amazon"],
        filters=[ec2.GetAmiFilterArgs(name="description", values=[ "Amazon Linux 2 *" ])]
)


bastion_ec2_instance = ec2.Instance(
        "bastion",
        instance_type='t2.micro',
        ami=ami.id,
        vpc_security_group_ids=[bastion_sg.id],
        key_name=keypair.key_name,
        subnet_id=pub_subnets[0],
        associate_public_ip_address=True,
        tags={
        'Name': 'bastion',
    },
)