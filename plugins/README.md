# Collections Plugins Directory

The `pcp_push` module is maintained in `roles/pcp/library/pcp_push.py`.
`plugins/modules/pcp_push.py` links to that file so the same implementation
works when PCP is used as a standalone or vendored role and as a collection
role. Tasks use the short module name to support both loading methods.

Consumers converting a wrapper role into another collection must also export
the nested PCP role's `library/pcp_push.py` to that collection's
`plugins/modules/`. Ansible does not load role-local libraries inside a
collection. The short task name allows the exported module to resolve in the
consumer's namespace without installing `performancecopilot.metrics` too.

This directory can be used to ship various plugins inside an Ansible collection. Each plugin is placed in a folder that
is named after the type of plugin it is in. It can also include the `module_utils` and `modules` directory that
would contain module utils and modules respectively.

Here is an example directory of the majority of plugins currently supported by Ansible:

```plain
└── plugins
    ├── action
    ├── become
    ├── cache
    ├── callback
    ├── cliconf
    ├── connection
    ├── filter
    ├── httpapi
    ├── inventory
    ├── lookup
    ├── module_utils
    ├── modules
    ├── netconf
    ├── shell
    ├── strategy
    ├── terminal
    ├── test
    └── vars
```

A full list of plugin types can be found at [Working With Plugins](https://docs.ansible.com/ansible/2.9/plugins/plugins.html).
