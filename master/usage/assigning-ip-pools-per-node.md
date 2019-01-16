---
title: Assigning IP pools per-Node
---

## About IP pool Node selection

Starting from {{site.prodname}} {{site.min-versions.ip-pool-node-select}}, IP pools can be configured 
to restrict IP address assignment of workloads to specific Nodes. You may want to assign the IP pool 
to a specific Node in order to (insert VISA's use-case here).

### Purpose of this page

Provide guidance on how to configure an IP pool to assign IPs to a specific, or group of, Node(s).

## Prerequisites

**{{site.prodname}} IPAM**

This guide only applies if you are using {{site.prodname}} IPAM.

**Labeled Nodes**

In order to assign certain IP pools to specific Nodes, these Nodes must be labeled. See the documentation for [calicoctl label]({{site.baseurl}}/{{page.version}}/reference/calicoctl/commands/label) and [kubectl label](https://kubernetes.io/docs/tasks/configure-pod-container/assign-pods-nodes/#add-a-label-to-a-node) for more information on how to do this.

### Example: Kubernetes

In this example, we created a cluster with kubeadm.  We wanted the pods to use IPs in the range
`10.0.0.0/16` so we set `--pod-network-cidr=10.0.0.0/16` when running `kubeadm init`.  However, we
installed {{ site.prodname }} without setting the default IP pool to match. Running `calicoctl get ippool -o wide` shows
{{site.prodname}} created its default IP pool of `192.168.0.0/16`:

```
NAME                  CIDR             NAT    IPIPMODE   DISABLED
default-ipv4-ippool   192.168.0.0/16   true   Always     false
```
{: .no-select-button}

Based on the output of `calicoctl get wep --all-namespaces`, we see `kube-dns` has already been allocated an address
from the wrong range:

```
NAMESPACE     WORKLOAD                   NODE      NETWORKS            INTERFACE
kube-system   kube-dns-6f4fd4bdf-8q7zp   vagrant   192.168.52.130/32   cali800a63073ed
```
{: .no-select-button}

Let's get started.

1. Add a new IP pool:

   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: new-pool
   spec:
     cidr: 10.0.0.0/16
     ipipMode: Always
     natOutgoing: true
   EOF
   ```

   We should now have two enabled IP pools, which we can see when running `calicoctl get ippool -o wide`:

   ```
   NAME                  CIDR             NAT    IPIPMODE   DISABLED
   default-ipv4-ippool   192.168.0.0/16   true   Always     false
   new-pool              10.0.0.0/16      true   Always     false
   ```
   {: .no-select-button}

2. Disable the old IP pool.

   First save the IP pool definition to disk:

       calicoctl get ippool -o yaml > pool.yaml

   `pool.yaml` should look like this:

   ```
   apiVersion: projectcalico.org/v3
   items:
   - apiVersion: projectcalico.org/v3
     kind: IPPool
     metadata:
       name: default-ipv4-ippool
     spec:
       cidr: 192.0.0.0/16
       ipipMode: Always
       natOutgoing: true
   - apiVersion: projectcalico.org/v3
     kind: IPPool
     metadata:
       name: new-pool
     spec:
       cidr: 10.0.0.0/16
       ipipMode: Always
       natOutgoing: true
   ```

   >Note: Some extra cluster-specific information has been redacted to improve
   readibility.

   Edit the file, adding `disabled: true` to the `default-ipv4-ippool` IP pool:

   ```
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: default-ipv4-ippool
   spec:
     cidr: 192.0.0.0/16
     ipipMode: Always
     natOutgoing: true
     disabled: true
   ```

   Apply the changes:

       calicoctl apply -f pool.yaml

   We should see the change reflected in the output of `calicoctl get ippool -o wide`:

   ```
   NAME                  CIDR             NAT    IPIPMODE   DISABLED
   default-ipv4-ippool   192.168.0.0/16   true   Always     true
   new-pool              10.0.0.0/16      true   Always     false
   ```
   {: .no-select-button}

3. Recreate all existing workloads using IPs from the disabled pool.
   In this example, kube-dns is the only workload networked by {{ site.prodname }}:

   ```
   kubectl delete pod -n kube-system kube-dns-6f4fd4bdf-8q7zp
   ```

   Check that the new workload now has an address in the new IP pool by running `calicoctl get wep --all-namespaces`:

   ```
   NAMESPACE     WORKLOAD                   NODE      NETWORKS            INTERFACE
   kube-system   kube-dns-6f4fd4bdf-8q7zp   vagrant   10.0.24.8/32   cali800a63073ed
   ```
   {: .no-select-button}

4. Delete the old IP pool:

   ```
   calicoctl delete pool default-ipv4-ippool
   ```

## Next Steps

For more information on the structure of the IP pool resource, see
[the IP pools reference]({{ site.baseurl }}/{{ page.version }}/reference/calicoctl/resources/ippool).
