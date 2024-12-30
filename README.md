# Amazon DCV Samples

Welcome to the DCV Samples repository within [AWS Samples](https://github.com/aws-samples). This repository will be used to host samples for Amazon DCV integrated workloads. These workloads include managed services that leverage DCV, such as [Amazon WorkSpaces](https://aws.amazon.com/workspaces/all-inclusive/) that stream with [WSP](https://docs.aws.amazon.com/workspaces/latest/adminguide/amazon-workspaces-protocols.html). 

## Glossary 
- [Bootstrap](./bootstrap/)
- [AWS Cloud Development Kit Examples](./cdk/)
- [Session Resolver](./session-resolver/)
- [DCV/WSP Usage Reports](./usage-reporting/)

## Overview

### Bootstrap 
The provided script `dcv-gateway-installer.sh` bootstraps the installation and configuration of the DCV Connection Gateway component. This can be injected with [Amazon EC2 user data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) or by running the script locally with `sudo`. To read more about the DCV Connection Gateway, see the [DCV Connection Gateway Administrator Guide](https://docs.aws.amazon.com/dcv/latest/gw-admin/what-is-gw.html).

The provided script `dcv-session-manager-installer.sh` bootstraps the installation and configuration of the DCV Session Manager component. This can be injected with [Amazon EC2 user data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) or by running the script locally with `sudo`. To read more about DCV Session Manager, see the [DCV Session Manager Administrator Guide](https://docs.aws.amazon.com/dcv/latest/sm-admin/what-is-sm.html).

The provided script `Install-DCVandSMAgent.ps1` bootstraps the installation and configuration of DCV server and DCV Session Manager agent. This can be injected with [Amazon EC2 user data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) or by running the script locally within an Administrator PowerShell terminal. Updating the `SESSION-MGR-PRIVATE-DNS` placeholder with the private DNS of DCV Session Manager allows the script to configure the host correctly. 

The provided script `Install-DCVandSMAgent.ps1` bootstraps the configuration of DCV server and DCV Session Manager agent. This can be injected with [Amazon EC2 user data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) or by running the script locally with `sudo`. Updating the `SESSION-MGR-PRIVATE-DNS` placeholder with the private DNS of DCV Session Manager allows the script to configure the host correctly. Note, this script will only work on a host that already has DCV server and DCV Session Manager agent installed. It is intended to be used with the Linux-based [AWS Marketplace DCV AMIs](https://aws.amazon.com/marketplace/seller-profile?id=74eff437-1315-4130-8b04-27da3fa01de1). 

### CDK
This folder contains several [AWS Cloud Development Kit](https://aws.amazon.com/cdk/) (AWS CDK) examples for deploying DCV workloads as IaaC. For an overview of the current CDK examples, see the [README](/cdk/README.md) in the cdk folder.

**Current CDK Examples**
- Deploy a DCV Session Manager and DCV Connection Gateway environment
- Deploy a DCV Session Manager and DCV Connection Gateway environment with EC2 Image Builder pipelines for both components
- Deploy DCV Access Console

### Session Resolver
The provided script provides logic to run in a AWS Lambda function to resolver DCV sessions streaming through a DCV Connection Gateway.  To learn more, see the [Build a serverless session resolver for your Amazon DCV Connection Gateway](https://aws.amazon.com/blogs/desktop-and-application-streaming/build-a-serverless-session-resolver-for-your-nice-dcv-connection-gateway/) AWS blog post.

### DCV/WSP Usage Reports 
The provided scripts to generate DCV usage reports on Windows illustrate how to use DCV calls to find when a user starts and ends their session. This allows administrators to generate granular usage reports that can be further modified to include additional information. For a walkthrough of how to implement these reports on a WSP Amazon WorkSpace, see this [blog post](https://aws.amazon.com/blogs/desktop-and-application-streaming/generate-custom-usage-reports-for-amazon-workspaces/).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
