from pulumi_aws import iam
import json
import pulumi

config = pulumi.Config()
data = config.require_object("data")

#EKS
eks_cluster_role = iam.Role(
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
)

iam.RolePolicyAttachment(
    'eks-cluster-policy-attachment',
    role=eks_cluster_role.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEKSClusterPolicy',
)

#node groups
#node group iam
node_role_spot = iam.Role(
    'node-role-spot',
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
)

node_role_ondemand = iam.Role(
    'node-role-ondemand',
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
)

iam.RolePolicyAttachment(
    'eks-node-pa-spot',
    role=node_role_spot.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy',
)

iam.RolePolicyAttachment(
    'eks-node-pa-ondemand',
    role=node_role_ondemand.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy',
)



iam.RolePolicyAttachment(
    'eks-cni-pa-spot',
    role=node_role_spot.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy',
)

iam.RolePolicyAttachment(
    'eks-cni-pa-ondemand',
    role=node_role_ondemand.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy',
)


iam.RolePolicyAttachment(
    'ecr-pa-spot',
    role=node_role_spot.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
)

iam.RolePolicyAttachment(
    'ecr-pa-ondemand',
    role=node_role_ondemand.id,
    policy_arn='arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
)