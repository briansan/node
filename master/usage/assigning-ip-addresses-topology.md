---
title: Assigning IP addresses based on topology
---

## Why this is useful

{{site.prodname}} can be configured to use specific IP pools for different
topological areas. For example, you may want workloads in a particular rack,
zone, or region to receive addresses from the same IP pool. This may be
desirable either to reduce the number of routes required in the network or to
meet requirements imposed by an external firewall device or policy. This guide
walks through an example of how to set this up.

## How this works
At a high level, this feature is operated by the setting node labels and then
selecting those nodes via node selector on your IP pool resources. Note that
there are a variety of other ways to specify IP address assignment behavior that
can be found in the [cni-plugin configuration reference document]({{site.baseurl}}/{{page.version}}/reference/cni-plugin/configuration).
Each approach has its own use-case but this particular one takes on the lowest
priority compared to the others. Specifying IP pools through
configuration takes precedence over IP addresses through annotations, which
takes precedence over IP pool assignment through node selectors.

## Prerequisites

This feature requires {{site.prodname}} for networking.

### Example: Kubernetes

In this example, we created a cluster with four nodes across two racks
(two nodes/rack). Consider the following:

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

Using the pod IP range `192.168.0.0/16`, we target the following setup: reserve
the `192.168.0.0/24` and `192.168.1.0/24` pools for `rack-0`, `rack-1`, `rack-2`
, and `rack-3` respectively. Let's get started.


By installing {{ site.prodname }} without setting the default IP pool to match,
running `calicoctl get ippool -o wide` shows that {{site.prodname}} created its
default IP pool of `192.168.0.0/16`:

```
NAME                  CIDR             NAT    IPIPMODE   DISABLED   SELECTOR
default-ipv4-ippool   192.168.0.0/16   true   Always     false      all()
```
{: .no-select-button}

1. Delete the default IP pool.

   Since the `default-ipv4-ippool` IP pool resource already exists and accounts
   for the entire `/16` block, we will have to delete this first:

   ```
   calicoctl delete ippools default-ipv4-ippool
   ```

2. Label the nodes.
   To assign IP pools to specific nodes, these nodes must be labelled
   using [kubectl label](https://kubernetes.io/docs/tasks/configure-pod-container/assign-pods-nodes/#add-a-label-to-a-node).

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

   We should now have two enabled IP pools, which we can see when running
   `calicoctl get ippool -o wide`:

   ```
   NAME                  CIDR             NAT    IPIPMODE   DISABLED   SELECTOR
   rack-1-ippool         192.168.0.0/24   true   Always     false      rack == "1"
   rack-2-ippool         192.168.1.0/24   true   Always     false      rack == "2"
   ```
   {: .no-select-button}

4. Verify that the IP pool node selectors are being respected.

   We will create an nginx deployment with five replicas to get a workload
   running on each node.

   ```
   kubectl create deployment nginx --image nginx
   kubectl scale deployment nginx --replicas 5
   ```

   Check that the new workloads now have an address in the proper IP pool
   allocated for rack that the node is on by running `kubectl get pods -owide`.

   ```
   NAME                   READY   STATUS    RESTARTS   AGE    IP             NODE          NOMINATED NODE   READINESS GATES
   nginx-5c7588df-prx4z   1/1     Running   0          6m3s   192.168.0.64   kube-node-0   <none>           <none>
   nginx-5c7588df-s7qw6   1/1     Running   0          6m7s   192.168.0.129  kube-node-1   <none>           <none>
   nginx-5c7588df-w7r7g   1/1     Running   0          6m3s   192.168.1.65   kube-node-2   <none>           <none>
   nginx-5c7588df-62lnf   1/1     Running   0          6m3s   192.168.1.1    kube-node-3   <none>           <none>
   nginx-5c7588df-pnsvv   1/1     Running   0          6m3s   192.168.1.64   kube-node-2   <none>           <none>
   ```
   {: .no-seleck-button}

   The grouping of IP address assigned to the workloads differ based on what
   node that they were scheduled to. Additionally, the assigned address for
   each workload falls within the respective IP pool that selects the proper
   rack that they run on.

> **Note**: {{site.prodname}} IPAM will not reassign IP addresses to workloads
> that are already running. To update running workloads with IP addresses from
> a newly configured IP pool, they must be recreated. We recommmend doing this
> before going into production or during a maintenance window.
{: .alert .alert-info}

## Related links

For more information on the structure of the IP pool resource, see
[the IP pools reference]({{ site.baseurl }}/{{ page.version }}/reference/calicoctl/resources/ippool).
