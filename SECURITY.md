# Security

## What Centinela protects and what it does not

Centinela reduces the risk that a message manipulates an AI assistant or the person who reads it. It is not a guarantee: a new or clever message can get past the guard. That is why the design puts the delicate decisions in code and, when in doubt, leaves them to a person.

## How to report a problem

If you find a way around the guard or the classifier, or any other security problem:

1. **Do not open a public issue** and do not publish the message that does it.
2. Use GitHub's private report: the **Security** tab of the repository, then **Report a vulnerability**.
3. Tell us which version you used, which detector was active and what you expected to happen.

We reply as soon as we can. Once the problem is fixed, we add a case to the benchmark so it does not happen again, crediting you if you want.

## Responsible use

- The benchmark contains attack messages because they are needed to measure defenses. They are translations of attacks that are already public and generic examples, not tools ready to attack a specific system.
- Do not use Centinela or its data to test third-party systems without written permission.
- Examples must not contain real personal data.
