---
title: Assigning IP pools per-Node
---

## About IP pool Node selection

Starting from {{site.prodname}} {{site.min-versions.ip-pool-node-select}}, IP pools can be configured 
to restrict IP address assignment of workloads to specific Nodes. This feature is useful for
network/system administrators that are interested in assigning IPs to pods based on rack affinity.
This guide walkthroughs an example of how to setup and manage this feature.

## Prerequisites

**{{site.prodname}} IPAM**

This guide only applies if you are using {{site.prodname}} IPAM.

**Labeled Nodes**

In order to assign IP pools to specific Nodes, these Nodes must be labeled. See the documentation for [calicoctl label]({{site.baseurl}}/{{page.version}}/reference/calicoctl/commands/label) and [kubectl label](https://kubernetes.io/docs/tasks/configure-pod-container/assign-pods-nodes/#add-a-label-to-a-node) for more information on how to do this. We recommend using `kubectl label`.

### Example: Kubernetes

In this example, we created a cluster with 8 nodes across 4 racks (2 nodes/rack). Consider the following:

```
       -------------------------------------------------------
       |                router                               |
       -------------------------------------------------------
       /                 |                 |                 \
---------------   ---------------   ---------------   ---------------   
| rack-0      |   | rack-1      |   | rack-2      |   | rack-3      |   
---------------   ---------------   ---------------   ---------------   
| kube-node-0 |   | kube-node-2 |   | kube-node-4 |   | kube-node-6 |   
- - - - - - - -   - - - - - - - -   - - - - - - - -   - - - - - - - -   
| kube-node-1 |   | kube-node-3 |   | kube-node-5 |   | kube-node-7 |   
- - - - - - - -   - - - - - - - -   - - - - - - - -   - - - - - - - -   
```

Using the pods IP range `192.168.0.0/16`, we will want to optimize our IP allocation strategy to assign IPs from 4 different pools for each rack.
For this example, we target the following setup: `192.168.0.0/18`, `192.168.64.0/18`, `192.168.128.0/18`, and `192.168.196.0/18` blocks
for `rack-0`, `rack-1`, `rack-2`, and `rack-3` respectively. Let's get started.


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
   kubectl label nodes kube-node-4 rack=2
   kubectl label nodes kube-node-5 rack=2
   kubectl label nodes kube-node-6 rack=3
   kubectl label nodes kube-node-7 rack=3
   ```
3. Create an IP pool for each rack.

   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: rack-0-ippool
   spec:
     cidr: 192.168.0.0/18
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
     cidr: 192.168.64.0/18
     ipipMode: Always
     natOutgoing: true
     nodeSelector: rack == "1"
EOF
   ```

   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: rack-2-ippool
   spec:
     cidr: 192.168.128.0/18
     ipipMode: Always
     natOutgoing: true
     nodeSelector: rack == "2"
EOF
   ```
	 
   ```
   calicoctl create -f -<<EOF
   apiVersion: projectcalico.org/v3
   kind: IPPool
   metadata:
     name: rack-3-ippool
   spec:
     cidr: 192.168.192.0/18
     ipipMode: Always
     natOutgoing: true
     nodeSelector: rack == "3"
EOF
   ```

   We should now have 4 enabled IP pools, which we can see when running `calicoctl get ippool -o wide`:

   ```
   NAME                  CIDR             NAT    IPIPMODE   DISABLED   SELECTOR
   rack-1-ippool         192.168.0.0/16   true   Always     false      rack == "1"
   rack-2-ippool         192.168.64.0/16  true   Always     false      rack == "2"
   rack-3-ippool         192.168.128.0/16 true   Always     false      rack == "3"
   rack-4-ippool         192.168.192.0/16 true   Always     false      rack == "4"
   ```
   {: .no-select-button}

3. Verify that the IP pool node selectors are being respected.

   We will create an nginx deploy with 10 replicas to get a workload running on each node.

   ```
   kubectl create deployment nginx --image nginx
   kubectl scale deployment nginx --replicas 10
   ```

   Check that the new workloads now have an address in the proper IP pool allocated for rack that the node is on by running `calicoctl get wep -owide`:

   ```
   NAME                                            WORKLOAD               NODE          NETWORKS            INTERFACE         PROFILES                          NATS
   kube--node--0-k8s-nginx--5c7588df--4g2b9-eth0   nginx-5c7588df-4g2b9   kube-node-0   192.168.7.129/32    cali79b6f790a38   kns.default,ksa.default.default
   kube--node--1-k8s-nginx--5c7588df--sl2wq-eth0   nginx-5c7588df-sl2wq   kube-node-1   192.168.54.128/32   calic790f38759d   kns.default,ksa.default.default
   kube--node--2-k8s-nginx--5c7588df--2bcgv-eth0   nginx-5c7588df-2bcgv   kube-node-2   192.168.89.192/32   calicd34697b75c   kns.default,ksa.default.default
   kube--node--3-k8s-nginx--5c7588df--dj66l-eth0   nginx-5c7588df-dj66l   kube-node-3   192.168.82.194/32   cali7a3f8f86b3a   kns.default,ksa.default.default
   kube--node--4-k8s-nginx--5c7588df--lzrhk-eth0   nginx-5c7588df-lzrhk   kube-node-4   192.168.153.193/32  calida5e7e2baf2   kns.default,ksa.default.default
   kube--node--5-k8s-nginx--5c7588df--8f7s3-eth0   nginx-5c7588df-8f7s3   kube-node-5   192.168.186.182/32  cali828a29388b8   kns.default,ksa.default.default
   kube--node--6-k8s-nginx--5c7588df--9buw3-eth0   nginx-5c7588df-9buw3   kube-node-6   192.168.208.195/32  cali9da8bcd8b9d   kns.default,ksa.default.default
   kube--node--7-k8s-nginx--5c7588df--a9b93-eth0   nginx-5c7588df-a9b93   kube-node-7   192.168.243.235/32  cali8ad8bc9de99   kns.default,ksa.default.default
   kube--node--3-k8s-nginx--5c7588df--g88s3-eth0   nginx-5c7588df-g88s3   kube-node-3   192.168.82.195/32   calid8c8a8deb38   kns.default,ksa.default.default
   kube--node--5-k8s-nginx--5c7588df--29t93-eth0   nginx-5c7588df-29t93   kube-node-5   192.168.186.183/32  cali88de0a9bcde   kns.default,ksa.default.default
   ```
   {: .no-seleck-button}

   Note how the third byte of the IP address assigned to the workload differ based on what node that they been scheduled to. 
   Additionally, the assigned address for each workload falls within the respective IP pool that selects the proper rack that they run on.
   Finally, observe how the third byte of workloads running on two different nodes of the same rack differ but still fall within the CIDR range specified by the IP pool (i.e. kube-node-0 has 7 and kube-node-1 has 54 as the third byte which are different values, but they both fall in the 192.168.0.0/18 range).

## Next Steps

For more information on the structure of the IP pool resource, see
[the IP pools reference]({{ site.baseurl }}/{{ page.version }}/reference/calicoctl/resources/ippool).
