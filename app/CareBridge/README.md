# CareBridge runtime

This is the AgentCore app folder from the [getting started sample](https://github.com/awslabs/agentcore-samples/tree/main/00-getting-started):

```
app/CareBridge/
├── main.py            # entrypoint AgentCore runs
├── parse.py
├── model/load.py      # Bedrock model
├── memory/session.py  # AgentCore Memory
├── pyproject.toml
└── carebridge/        # the agent package
```

`main.py` is the file `agentcore deploy` runs. The package next to it is the same code the local API imports.
