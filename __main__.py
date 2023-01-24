from pulumi_aws import ec2,iam,eks,rds
import pulumi
import network
import json

config = pulumi.Config()
data = config.require_object("data")

class StartonEksCluster(pulumi.ComponentResource):
    def __init__(self, name,version="1.23", vpc=None,eks_subnets=[],authorized_api_cidrs=["0.0.0.0/0"],node_pools=[],bastion_sg=None,with_bastion=False, opts=None):
        super().__init__('pkg:index:StartonEksCluster', name, None, opts)
        child_opts = pulumi.ResourceOptions(parent=self)
        self.name = name
        self.version=version
        self.eks_subnets = eks_subnets
        self.authorized_api_cidrs=authorized_api_cidrs
        #self.node_pools=node_pools
        self.bastion_sg=bastion_sg
        self.vpc=vpc
        self.node_groups=[]

        self.set_security_groups(with_bastion,bastion_sg,child_opts)
        self.create_controlplane(child_opts)
        self.create_node_groups(node_pools,child_opts)

    def create_controlplane(self,child_opts):
        #EKS
        self.eks_cluster_role = iam.Role(
            f'eks-cluster-role-{self.name}',
            assume_role_policy=json.dumps({
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Action': 'sts:AssumeRole',
                        'Principal': {
                            'Service': 'eks.amazonaws.com'
                        },
                        'Effect': 'Allow',
                        'Sid': ''
                    }
                ],
            }),
            opts=child_opts,
            tags={
                'Name': f'eks-cluster-role-{self.name}',
            },
        )

        iam.RolePolicyAttachment(
            'eks-cluster-policy-attachment',
            role=self.eks_cluster_role.id,
            policy_arn='arn:aws:iam::aws:policy/AmazonEKSClusterPolicy',
            opts=child_opts
        )
        self.eks_cluster = eks.Cluster(
            f'eks-cluster-{self.name}',
            role_arn=self.eks_cluster_role.arn,
            version = self.version,
            tags={
                'Name': f'eks-cluster-{self.name}',
            },
            vpc_config=eks.ClusterVpcConfigArgs(
                public_access_cidrs=authorized_api_cidrs,
                security_group_ids=[self.controlplane_sg.id],
                subnet_ids=eks_subnets,
            ),
            opts=child_opts
        )
        self.register_outputs({
            "cluster_id": self.eks_cluster.cluster_id
        })

    def build_taints(self, taints_list):
        taints = []
        for taint in taints_list:
            taints.append(eks.NodeGroupTaintArgs(effect=taint["effect"],key=taint["key"],value=taint["value"]))
        return taints


    def create_node_groups(self,node_pools,child_opts=None):
        for node in node_pools:
            node_launch_template = ec2.LaunchTemplate(resource_name=f'{node["name"]}-template',instance_type=node["instance_type"],
                        key_name=node["key_name"],
                        network_interfaces=[ec2.LaunchTemplateNetworkInterfaceArgs(
                            associate_public_ip_address="false",
                            security_groups = [self.nodes_sg.id],
                        )],
                        opts=child_opts
            )

            node_role = self.build_node_role(node["name"],child_opts)

            node_group =  eks.NodeGroup(
                f'eks-{node["name"]}-node-group',
                cluster_name=self.eks_cluster.name,
                node_group_name=f'eks-{node["name"]}-node-group',
                node_role_arn=node_role.arn,
                subnet_ids=node["subnets"],
                capacity_type=node["capacity_type"],
                taints=self.build_taints(node["taints"]),
                launch_template = eks.NodeGroupLaunchTemplateArgs(id=node_launch_template.id,version=node_launch_template.latest_version),

                tags={
                    'Name': f'eks-{node["name"]}-node-group',
                },
                opts=child_opts,
                scaling_config=eks.NodeGroupScalingConfigArgs(
                    desired_size=node["desired_size"],
                    max_size=node["max_size"],
                    min_size=node["min_size"],
                ),
            )
            self.node_groups.append(node_group)




    def set_security_groups(self,with_bastion=False,bastion_sg=None,child_opts=None):
        self.controlplane_sg = ec2.SecurityGroup(
                resource_name='controlplane-sg',
                vpc_id=self.vpc.id,
                description="EKS controlplane security group",
            egress=[
                {
                    "protocol": "-1",
                    "from_port": 0,
                    "to_port": 0,
                    "cidr_blocks": ["0.0.0.0/0"],
                }
            ],
                tags={
                'Name': f'controlplane-sg',
            },
            opts=child_opts
        )

        self.nodes_sg = ec2.SecurityGroup(
                resource_name='nodes-sg',
                vpc_id=self.vpc.id,
                description="EKS dataplane security group",
                ingress=[
                {#controlplane to nodes
                    "protocol": "tcp",
                    "from_port": 443,
                    "security_groups": [self.controlplane_sg.id],
                    "to_port": 443,
                },
                {
                    "protocol": "tcp",
                    "from_port": 10250,
                    "security_groups": [self.controlplane_sg.id],
                    "to_port": 10250,
                },
                {#node to coredns
                    "protocol": "tcp",
                    "from_port": 53,
                    "to_port": 53,
                    "self": True
                },
                {
                    "protocol": "udp",
                    "from_port": 53,
                    "to_port": 53,
                    "self": True
                },
                {#ssh between bastion and nodes
                    "protocol": "tcp",
                    "from_port": 22,
                    "security_groups": [bastion_sg.id],
                    "to_port": 22,
                    "self": True
                },
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
                'Name': f'nodes-sg',
            },
            opts=child_opts
        )

        ec2.SecurityGroupRule("Allow Nodes to control plane",
                    type="ingress",
                    from_port=443,
                    to_port=443,
                    protocol="tcp",
                    source_security_group_id=self.nodes_sg.id,
                    security_group_id=self.controlplane_sg.id,
                    opts=child_opts)

        if with_bastion and bastion_sg:
         ec2.SecurityGroupRule("Allow Bastion to nodes",
                              type="ingress",
                              from_port=22,
                              to_port=22,
                              protocol="tcp",
                              source_security_group_id=bastion_sg.id,
                              security_group_id=self.nodes_sg.id,
                              opts=child_opts)





    def build_node_role(self,name,child_opts=None):

        node_role = iam.Role(
            f'node-role-{name}',
            assume_role_policy=json.dumps({
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Action': 'sts:AssumeRole',
                        'Principal': {
                            'Service': 'ec2.amazonaws.com'
                        },
                        'Effect': 'Allow',
                        'Sid': ''
                    }
                ],
            }),
            opts=child_opts,
            tags={
                'Name': f'node-role-{name}',
            },
        )

        iam.RolePolicyAttachment(
            f'eks-node-pa-{name}',
            role=node_role.id,
            policy_arn='arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy',
            opts=child_opts
        )



        iam.RolePolicyAttachment(
            f'eks-cni-pa-{name}',
            role=node_role.id,
            policy_arn='arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy',
            opts=child_opts
        )


        iam.RolePolicyAttachment(
            f'ecr-pa-{name}',
            role=node_role.id,
            policy_arn='arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
            opts=child_opts
        )
        return node_role


    def set_iam(self,child_opts):
        self.eks_cluster_role = iam.Role(
            'eks-cluster-role',
            assume_role_policy=json.dumps({
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Action': 'sts:AssumeRole',
                        'Principal': {
                            'Service': 'eks.amazonaws.com'
                        },
                        'Effect': 'Allow',
                        'Sid': ''
                    }
                ],
            }),
            opts=child_opts
        )

        iam.RolePolicyAttachment(
            'eks-cluster-policy-attachment',
            role=self.eks_cluster_role.id,
            policy_arn='arn:aws:iam::aws:policy/AmazonEKSClusterPolicy',
            opts=child_opts
        )


eks_subnets=network.priv_subnets
authorized_api_cidrs = ["0.0.0.0/0"]
node_pools = [
    {
        "name" : "ondemand",
        "capacity_type": "ON_DEMAND",
        "key_name": network.keypair.key_name,
        "subnets": network.priv_subnets,
        "instance_type": "t2.micro",
        "taints": [],
        "desired_size": 2,
        "max_size": 2,
        "min_size": 1,
    },
    {
        "name" : "spot",
        "capacity_type": "SPOT",
        "key_name": network.keypair.key_name,
        "subnets": network.priv_subnets,
        "instance_type": "t3.micro",
        "taints": [{"effect":"NO_SCHEDULE","key":"spot","value":"true"}],
        "desired_size": 1,
        "max_size": 1,
        "min_size": 1,
    },
]

eks_cluster = StartonEksCluster('starton-test', vpc=network.vpc, eks_subnets=eks_subnets,node_pools=node_pools,with_bastion=True,bastion_sg=network.bastion_sg)

pulumi.export("cluster_name", eks_cluster.eks_cluster.id)


#RDS

rds_sg = ec2.SecurityGroup(
        resource_name='rds-sg',
        vpc_id=network.vpc.id,
        description="Allow SSH traffic to Bastion",
        ingress=[
        {
            "protocol": "tcp",
            "from_port": 5432,
            "to_port": 5432,
            "security_groups": [eks_cluster.nodes_sg.id],
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
        'Name': f'rds-sg',
    },
)

rds_subnetgroup = rds.SubnetGroup("rds-subnet-group",
    subnet_ids= network.priv_subnets,
    tags={
        "Name": "RDS private subnet group",
    })


rds_database = rds.Instance("rds-database",
    allocated_storage="10",
    db_name="eks",
    engine="postgres",
    engine_version="13.7",
    db_subnet_group_name=rds_subnetgroup.name,
    instance_class="db.t3.micro",
    password=data.get("rds_password"),
    publicly_accessible=False,
    skip_final_snapshot=True,
    username="eks",
    vpc_security_group_ids=[rds_sg.id])