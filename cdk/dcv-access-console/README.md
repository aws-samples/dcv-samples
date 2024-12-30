# Amazon DCV Access Console Deployment

Accelerate [Amazon DCV Access Console](https://docs.aws.amazon.com/dcv/latest/access-console/what-is-access-console.html) deployments with the AWS Cloud Development Kit (AWS CDK). This CDK will create a single Amazon Elastic Compute Cloud (Amazon EC2) instance to host all of the required DCV Access Console components.

## Overview
The architecture diagram below depicts the resources that this solution will deploy into your account. This CDK will only deploy the DCV Access Console. An existing DCV Session Manager environment is required. The DCV Connection Gateway in the diagram is optional.

![Figure1: Architecture](./documentation/images/SolutionArchitecture.png) 

Figure 1: AWS CDK that will deploy and configure a DCV Access Console on a single instance in an existing DCV Session Manager environment.

## Prerequisites
- An AWS account with full permissions on:
    - AWS Systems Manager Parameter Store
    - AWS Systems Manager Session Manager
    - Amazon Elastic Compute Cloud (Amazon EC2) 
    - Amazon VPC
- A system with the following installed:
    - AWS CLI 
    - AWS CDK 
    - Node.js
    - Python
    - Git
- Basic understanding of:
    - AWS Cloud 
    - DCV usage
    - Scripting languages (Python, Bash)

# AWS VPC Infrastructure Creation with CDK
This example creates:
- A single EC2 instance hosting the DCV Access Console
- Systems Manager Parameter Store parameters
- IAM role for Access Console
- Security Group for Access Console

>Note: An SSH key-pair (.pem) is required to be registered in your AWS account and region. This key-pair name needs to be entered in the `config.json` file before deploying the infra stack in order to allow SSH access into the instance.

## Step 1: NPM 
The LTS version of [npm](https://www.npmjs.com/) is recommended. If npm is already on your system, upgrade npm to the latest version.

```bash
npm install -g npm@latest
```

## Step 2: AWS CDK 

Ensure that the latest [aws-cdk](https://aws.amazon.com/cdk/) is installed. 

```bash
npm install -g aws-cdk
```

Once installed, the following command confirms the installation was successful.

```bash
cdk --version
```

## Step 3: AWS CLI 
Install [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)


## Step 4: Git
Install [Git](https://git-scm.com/)

## Step 5: Clone the repository
Visit [clone a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository) for instructions. Clone this repository locally. 

## Step 6: Create a virtual environment
Open up a command line terminal of your choice.
### Windows
```bash
virtualenv --python <PATH-TO-PYTHON-VERSION-EXE> dcv-env
.\dcv-env\Scripts\activate
```

### macOS/Linux
```bash
virtualenv --python <PATH-TO-PYTHON-VERSION-BINARY> dcv-env
source dcv-env/bin/activate
```

## Step 7: Install Project Dependencies
Change directory into the **cdk** folder of the cloned repository. Install project dependencies.

```bash
pip install -r requirements.txt
```

## Step 8: Assume IAM role 
[Use an IAM role in the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html). 
> Note: To confirm your credentials are associated with the correct AWS account, you can run the following AWS CLI command - 

```bash
aws sts get-caller-identity 
```
(See [get-caller-identity](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/sts/get-caller-identity.html) in the AWS CLI documentation). 

## Step 9: CDK Bootstrap
[Bootstrap your AWS CDK environment. ](https://docs.aws.amazon.com/cdk/v2/guide/cli.html#cli-bootstrap)
Replace with your desired account number and region.

```bash 
cdk bootstrap 1234567890/us-east-1
```

## Step 10: Set AWS Account and Region for Infrastructure
Set the AWS account id and region by specifying in `/config.json` 
```bash
{
    ...
    "accountId": "xxxxxxxxxxxx",
    "region": "xx-xxxx-x",
    ...
}
```

Ensure the region is set in your AWS credentials by running the following command by replacing `us-east-1` with  your intended region:

For Windows:
```bash
set AWS_REGION=us-east-1
```
For Mac/Linux:
```bash
export AWS_REGION=us-east-1
```

## Step 11: Key Pairs for EC2
Use your own Key Pair or [Create Key Pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/create-key-pairs.html) for accessing the EC2s.

Use the Key Pair value for *sshKeypairName* in `/config.json` 

```bash
{
	"accountId": "xxxxxxxxxxxx",
    ...
    "sshKeypairName": "xxxxxxxxxxxxxxx",
    ...
}
```

## Step 12: AWS Key Management Service (KMS)
Choose to use the AWS provide default KMS or [Create Keys](href="https://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html).

Use the KMS value for kms_key_name in `/config.json`

```bash
{
	"accountId": "xxxxxxxxxxxx",
    ...
    "kmsKeyName": "aws/ebs",
    ...
}
```

## Step 13: Networking
Provide the network details for where the DCV Access Console should be provisioned. This includes the VPC ID, Subnet ID, and Availability Zone (ie. us-east-1a).

**Note:** If you provide a private subnet, it needs to have a route to a NAT Gateway to download components. Private deployments can only be accessed on the private network. 

```json
{
    ...
    "network" : {
            "vpcId": "vpc-xxxxxxxxxxxxxxxxx",
            "accessConsoleSubnetId": "subnet-xxxxxxxxxxxxxxxxx",
            "subnetAZ": "xx-xxxx-xx"
    }, ...
}
```


## Step 14: Update the Access Console parameters
This CDK is intended to deployed in an existing DCV Session Manager environment. Update the `config.json` parameters to align to your existing environment.

### amiId
This CDK is intended to be deployed using the ARM-based Amazon Linux 2023 AMI. This can be found within the [AMI Catalog](https://console.aws.amazon.com/ec2/home?#AMICatalog:).

If you would like to use a different [supported distribution for DCV Access Console](https://docs.aws.amazon.com/dcv/latest/access-console/requirements.html), ensure you meet the following AMI checklist. 

**AMI Checklist**
- The provided AMI is based on a [supported distribution for DCV Access Console](https://docs.aws.amazon.com/dcv/latest/access-console/requirements.html).
- Ensure your provided AMI is up to date and has the [AWS CLI](https://aws.amazon.com/cli/) installed.
- The CDK assumes you are using ARM-based AMIs so you can benefit from [EC2 Graviton](https://aws.amazon.com/ec2/graviton/). If you would like to use an x86-based AMI, you may update the statically configured instance types in *dcv_ac_infra.py*.
- To utilize AWS Systems Manager Session Manager for access, ensure [SSM Agent](https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html) is installed within your AMI. 

**Note:** If you plan to use Ubuntu, it is recommended you run the [installation wizard](https://docs.aws.amazon.com/dcv/latest/access-console/using-setup-wizard.html) manually. Modify *access-console-user-data.py* to align to the Ubuntu commented caveats (comment out wizard call and uncomment the TMP_DIR).

### sessionMgrDns
This parameter is the private DNS name of your DCV Session Manager. This parameter configures the DCV Access Console to contact DCV Session Manager through the provided DNS name. 

### DCV Session Manager credentials
To interact with DCV Session Manager, the client needs to have registered credentials. If you do not have registered credentials for DCV Session Manager, see *Prerequisites* in the [DCV Access Console Administrator Guide](https://docs.aws.amazon.com/dcv/latest/access-console/prerequisites.html). These credentials are stored in SSM Parameter Store so the Access Console instance can retrieve them. Users with Identity Access Management permissions that permit access to the parameter will also be able to retrieve the credentials. 

- **smClientId** - Provide your registered Client ID.
- **smClientPsw** - Provide your registered Client Password.

### adminUser
This CDK configures the DCV Access Console to use *system-auth*, which redirects the credentials to the PAM module on the DCV Access Console host. On Amazon Linux 2023, the default created user is *ec2-user*. If you choose use this user for testing, connect to the DCV Access Console with SSM Session Manager and set a password for *ec2-user*. For example, `sudo passwd ec2-user`.

### gatewayDns (Optional)
If your existing environment utilizes a [DCV Connection Gateway](https://docs.aws.amazon.com/dcv/latest/gw-admin/what-is-gw.html), provide the DNS name for the gateway in this parameter. If you front your gateways with a NLB, provide the DNS name of the NLB. 

**If you do not use a gateway, leave this parameter blank.**


### inboundAccess
This parameter configures the inbound access on the DCV Access Console Security Group. By default, the connection is made on port 443. If you would like to isolate this to a specific IP range, update this parameter.

**The default parameter allows 443 traffic from anywhere**

Example config.json

```bash
{
    ...
    "accessConsole" : {
        "amiId": "ami-xxxxxxxxxxxxxxxxx",
        "sessionMgrDns": "PRIVATE-BROKER-DNS",
        "smClientId": "ASIAIOSFODNN7EXAMPLE",
        "smClientPsw": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "adminUser": "ec2-user",
        "gatewayDns": "",
        "inboundAccess": "0.0.0.0/0"
    }
}
```

## Step 15: Check Project with Synth
Verify there are no errors with the cloned project with [cdk synth](https://docs.aws.amazon.com/cdk/v2/guide/cli.html#cli-synth) (synthesize). 
```bash
cdk synth --all
```

## Step 16: Deploy DCV Access Console stack
```bash
cdk deploy
```

## Step 17: Testing your Configuration
After your deployment is finished, the CDK the output the URL of your DCV Access Console. Once the underlying EC2 instance is passing health checks, you can access the DCV Access Console through this URL. For usage instructions, see *Getting started with the Amazon DCV Session Manager console* in the [DCV Access Console Administrator Guide](https://docs.aws.amazon.com/dcv/latest/access-console/getting-started.html)

## Cleanup your Environment
To destroy all infrastructure contained in the CDK, run the following command:
```bash
cdk destroy
```

## Troubleshooting DCV Access Console
See the *Troubleshooting* section of the [DCV Access Console Administrator Guide](https://docs.aws.amazon.com/dcv/latest/access-console/troubleshooting.html).

The bash bootstrap creates a log file located at `/var/log/dcv-access-console-install.log`. This bootstrap builds your configuration file (`onebox-config-input.json`) and passes it into the [DCV Access Console Setup Wizard](https://docs.aws.amazon.com/dcv/latest/access-console/using-setup-wizard.html). The installation is placed within a temporary directory, which can be found in the bootstrap log. The Setup Wizard created detailed installation logs within the `output` directory. If you find the installation failed on a step, you may run the installation again. This can be performed by connecting to the Access Console instance with AWS SSM Session Manager and running the following command from within the installation directory:

`sudo python3 wizard.py --is-onebox --input-json onebox-config-input.json --force`

## CDK Feedback
If you have issues or feedback, open an issue on the Github repository. Note, this CDK is licensed as MIT-0. As-is examples are not supported by AWS Support. 

## Authors and acknowledgment
[Andrew Morgan](https://github.com/morgnza)<br>

## License
MIT License