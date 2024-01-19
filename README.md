## NICE DCV Samples

Welcome to the DCV Samples repository within [AWS Samples](https://github.com/aws-samples). This repository will be used to host samples for NICE DCV integrated workloads. These workloads include managed services that leverage DCV, such as [Amazon WorkSpaces](https://aws.amazon.com/workspaces/all-inclusive/) that stream with [WSP](https://docs.aws.amazon.com/workspaces/latest/adminguide/amazon-workspaces-protocols.html). 

### Glossary 
- Bootstrap
- Session Resolver 
- DCV/WSP Usage Reports 

### Overview

#### Bootstrap 
The provided script bootstraps a DCV Connection Gateway to install and configure the gateway component. This can be injected with [Amazon EC2 user data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) or by running the script locally with `sudo`.

#### Session Resolver
The provided script provides logic to run in a AWS Lambda function to resolver DCV sessions streaming through a DCV Connection Gateway.  To learn more, see the [Build a serverless session resolver for your NICE DCV Connection Gateway](https://aws.amazon.com/blogs/desktop-and-application-streaming/build-a-serverless-session-resolver-for-your-nice-dcv-connection-gateway/) AWS blog post.

#### DCV/WSP Usage Reports 
The provided scripts to generate DCV usage reports on Windows illustrate how to use DCV calls to find when a user starts and ends their session. This allows administrators to generate granular usage reports that can be further modified to include additional information. For a walkthrough of how to implement these reports on a WSP Amazon WorkSpace, see this [blog post](https://aws.amazon.com/blogs/desktop-and-application-streaming/generate-custom-usage-reports-for-amazon-workspaces/).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
