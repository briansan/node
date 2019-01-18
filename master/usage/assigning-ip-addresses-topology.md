---
title: Assigning IP Addresses based on Topology
---

## Why this is useful

{{site.prodname}} can be configured to use specific IP pools for different topological areas.
For example, you may want workloads in a particular rack, zone, or region to receive addresses from the same IP pool.
This may be desirable either to reduce the number of routes required in the network or to meet requirements imposed by an external firewall device or policy.
This guide walkthroughs an example of how to set this up.

## How this works
At a high level, this feature is operated by the setting node labels and then selecting those
nodes via node selector on your IP pool resources. Note that there are a variety of other ways
to specify IP address assignment behavior that can be found in the
[cni-plugin configuration reference document]({{site.baseurl}}/{{page.version}}/reference/cni-plugin/configuration).
Each approach has its own use-case but this particular one takes on the lowest priority
compared to the others (i.e. Specifying IP pools through configuration has precendence
over IP addresses through annotations which has precendence over this IP pool
assignment through node selectors).

## Prerequisites

**{{site.prodname}} IPAM**

This guide only applies if you are using {{site.prodname}} IPAM.

**Labeled Nodes**

In order to assign IP pools to specific Nodes, these Nodes must be labeled. See the documentation for [calicoctl label]({{site.baseurl}}/{{page.version}}/reference/calicoctl/commands/label) and [kubectl label](https://kubernetes.io/docs/tasks/configure-pod-container/assign-pods-nodes/#add-a-label-to-a-node) for more information on how to do this. We recommend using `kubectl label`.

### Example: Kubernetes

In this example, we created a cluster with 4 nodes across 2 racks (2 nodes/rack). Consider the following:

```
       -------------------
       |    router       |
       -------------------
       |                 |
---------------   ---------------
| rack-0      |   | rack-1      |
---------------   ---------------
| kube-node-0 |   | kube-node-2 |
- - - - - - - -   - - - - - - - -
| kube-node-1 |   | kube-node-3 |
- - - - - - - -   - - - - - - - -
```

Using the pods IP range `192.168.0.0/16`, we target the following setup: reservet the `192.168.0.0/24` and `192.168.1.0/24` blocks for `rack-0`, `rack-1`, `rack-2`, and `rack-3` respectively.
Let's get started.


By installing {{ site.prodname }} without setting the
default IP pool to match, running `calicoctl get ippool -o wide` shows that {{site.prodname}} 
created its default IP pool of `192.168.0.0/16`:

```
NAME                  CIDR             NAT    IPIPMODE   DISABLED
default-ipv4-ippool   192.168.0.0/16   true   Always     false
```
{: .no-select-button}

1. Delete the default IP pool.

	Since the `default-ipv4-ippool` IP pool resource already exists and accounts for the entire `/16` block, we will have to delete this first:

   ```
   calicoctl delete ippools default-ipv4-ippool
   ```

2. Label the nodes.
   ```
   kubectl label nodes kube-node-0 rack=0
   kubectl label nodes kube-node-1 rack=0
   kubectl label nodes kube-node-2 rack=1
   kubectl label nodes kube-node-3 rack=1 
   ```
3. Create an IP pool for each rack.

   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: rack-0-ippool
   spec:
     cidr: 192.168.0.0/24
     ipipMode: Always
     natOutgoing: true
     nodeSelector: rack == "0"
EOF
   ```

   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: rack-1-ippool
   spec:
     cidr: 192.168.1.0/24
     ipipMode: Always
     natOutgoing: true
     nodeSelector: rack == "1"
EOF
   ```

   We should now have 2 enabled IP pools, which we can see when running `calicoctl get ippool -o wide`:

   ```
   NAME                  CIDR             NAT    IPIPMODE   DISABLED   SELECTOR
   rack-1-ippool         192.168.0.0/24   true   Always     false      rack == "1"
   rack-2-ippool         192.168.1.0/24   true   Always     false      rack == "2"
   ```
   {: .no-select-button}

4. Verify that the IP pool node selectors are being respected.

   We will create an nginx deploy with 5 replicas to get a workload running on each node.

   ```
   kubectl create deployment nginx --image nginx
   kubectl scale deployment nginx --replicas 5
   ```

   Check that the new workloads now have an address in the proper IP pool allocated for rack that the node is on by running `calicoctl get wep -owide`:

   ```
   NAME                                            WORKLOAD               NODE          NETWORKS            INTERFACE         PROFILES                          NATS
   kube--node--0-k8s-nginx--5c7588df--4g2b9-eth0   nginx-5c7588df-4g2b9   kube-node-0   192.168.0.65/32    cali79b6f790a38   kns.default,ksa.default.default
   kube--node--1-k8s-nginx--5c7588df--sl2wq-eth0   nginx-5c7588df-sl2wq   kube-node-1   192.168.0.97/32    calic790f38759d   kns.default,ksa.default.default
   kube--node--2-k8s-nginx--5c7588df--2bcgv-eth0   nginx-5c7588df-2bcgv   kube-node-2   192.168.1.33/32    calicd34697b75c   kns.default,ksa.default.default
   kube--node--3-k8s-nginx--5c7588df--dj66l-eth0   nginx-5c7588df-dj66l   kube-node-3   192.168.1.129/32   cali7a3f8f86b3a   kns.default,ksa.default.default
   kube--node--2-k8s-nginx--5c7588df--lzrhk-eth0   nginx-5c7588df-lzrhk   kube-node-2   192.168.1.34/32    calida5e7e2baf2   kns.default,ksa.default.default
   ```
   {: .no-seleck-button}

   Note how the fourth byte of the IP address assigned to the workload differ based on what node that they been scheduled to. 
   Additionally, the assigned address for each workload falls within the respective IP pool that selects the proper rack that they run on.

## Related Links

For more information on the structure of the IP pool resource, see
[the IP pools reference]({{ site.baseurl }}/{{ page.version }}/reference/calicoctl/resources/ippool).
