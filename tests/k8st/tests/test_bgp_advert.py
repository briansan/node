# Copyright (c) 2018-2019 Tigera, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os
import subprocess
from time import sleep

from kubernetes import client, config

from tests.k8st.test_base import TestBase

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


bird_conf = """
router id 10.192.0.5;

# Configure synchronization between routing tables and kernel.
protocol kernel {
  learn;             # Learn all alien routes from the kernel
  persist;           # Don't remove routes on bird shutdown
  scan time 2;       # Scan kernel routing table every 2 seconds
  import all;
        export all;
  graceful restart;  # Turn on graceful restart to reduce potential flaps in
                     # routes when reloading BIRD configuration.  With a full
                     # automatic mesh, there is no way to prevent BGP from
                     # flapping since multiple nodes update their BGP
                     # configuration at the same time, GR is not guaranteed to
                     # work correctly in this scenario.
  merge paths on;
}

# Watch interface up/down events.
protocol device {
  debug { states };
  scan time 2;    # Scan interfaces every 2 seconds
}

protocol direct {
  debug { states };
  interface -"cali*", "*"; # Exclude cali* but include everything else.
}

# Template for all BGP clients
template bgp bgp_template {
  debug { states };
  description "Connection to BGP peer";
  local as 64512;
  multihop;
  gateway recursive; # This should be the default, but just in case.
  import all;        # Import all routes, since we don't know what the upstream
                     # topology is and therefore have to trust the ToR/RR.
  export all;
  source address 10.192.0.5;  # The local address we use for the TCP connection
  add paths on;
  graceful restart;  # See comment in kernel section about graceful restart.
  connect delay time 2;
  connect retry time 5;
  error wait time 5,30;
}

# ------------- Node-to-node mesh -------------
# For peer /host/kube-master/ip_addr_v4
protocol bgp Mesh_10_192_0_2 from bgp_template {
  neighbor 10.192.0.2 as 64512;
  passive on; # Mesh is unidirectional, peer will connect to us.
}


# For peer /host/kube-node-1/ip_addr_v4
protocol bgp Mesh_10_192_0_3 from bgp_template {
  neighbor 10.192.0.3 as 64512;
  passive on; # Mesh is unidirectional, peer will connect to us.
}

# For peer /host/kube-node-2/ip_addr_v4
protocol bgp Mesh_10_192_0_4 from bgp_template {
  neighbor 10.192.0.4 as 64512;
  passive on; # Mesh is unidirectional, peer will connect to us.
}
"""


class TestBGPAdvert(TestBase):
    def setUp(self):
        # Run tearDown in case anything was left up
        self.tearDown()

        # # Setup external node: use privileged mode for setting routes
        subprocess.check_call("docker run -d "
                              "--privileged "
                              "--name kube-node-extra "
                              "--network kubeadm-dind-net "
                              "mirantis/kubeadm-dind-cluster:v1.10",
                              shell=True)
        # Install bird on extra node
        subprocess.check_call("docker exec kube-node-extra apt update", shell=True)
        subprocess.check_call("docker exec kube-node-extra apt install -y bird", shell=True)
        subprocess.check_call("docker exec kube-node-extra mkdir /run/bird", shell=True)
        with open('bird.conf', 'w') as birdconfig:
            birdconfig.write(bird_conf)
        subprocess.check_call("docker cp bird.conf kube-node-extra:/etc/bird/bird.conf", shell=True)
        subprocess.check_call("rm bird.conf", shell=True)
        subprocess.check_call("docker exec kube-node-extra service bird restart", shell=True)

        # # Create nginx deployment and service
        # subprocess.check_call("kubectl create deploy nginx --image=nginx", shell=True)
        # subprocess.check_call("kubectl create svc clusterIP nginx --tcp 80:80", shell=True)
        cluster = self.k8s_client()
        cluster.create_namespace(client.V1Namespace(metadata=client.V1ObjectMeta(name="bgp-test")))
        container = client.V1Container(
            name="nginx",
            image="nginx:1.7.9",
            ports=[client.V1ContainerPort(container_port=80)])
        # Create and configure a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": "nginx"}),
            spec=client.V1PodSpec(containers=[container]))
        # Create the specification of deployment
        spec = client.ExtensionsV1beta1DeploymentSpec(
            replicas=2,
            template=template)
        # Instantiate the deployment object
        nginx_deployment = client.ExtensionsV1beta1Deployment(
            api_version="extensions/v1beta1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name="nginx"),
            spec=spec)
        api_response = client.ExtensionsV1beta1Api().create_namespaced_deployment(
            body=nginx_deployment,
            namespace="bgp-test")
        _log.debug("Deployment created. status='%s'" % str(api_response.status))

        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name="nginx",
                labels={"name": "nginx"},
            ),
            spec={
                "ports": [{"port": 80}],
                "selector": {"app": "nginx"},
            }
        )
        api_response = cluster.create_namespaced_service(
            body=service,
            namespace="bgp-test",
        )
        _log.debug("Service created. status='%s'" % str(api_response.status))

        # # Modify calico/node to run :master tag and set CALICO_STATIC_ROUTES=10.96.0.0/12

        config.load_kube_config(os.environ.get('KUBECONFIG'))
        api = client.AppsV1Api(client.ApiClient())
        node_ds = api.read_namespaced_daemon_set("calico-node", "kube-system", exact=True, export=True)
        for container in node_ds.spec.template.spec.containers:
            if container.name == "calico-node":
                container.image = "calico/node:latest-amd64"
                route_env_present = False
                for env in container.env:
                    if "CALICO_STATIC_ROUTES" in env.name:
                        route_env_present = True
                if not route_env_present:
                    container.env.append({"name": "CALICO_STATIC_ROUTES", "value": "10.96.0.0/12", "value_from": None})
        api.replace_namespaced_daemon_set("calico-node", "kube-system", node_ds)

        # # Establish BGPPeer from cluster nodes to node-extra using calicoctl
        subprocess.check_call("""kubectl exec -i -n kube-system calicoctl -- /calicoctl apply -f - << EOF
apiVersion: projectcalico.org/v3
kind: BGPPeer
metadata:
  name: node-extra.peer
spec:
  peerIP: 10.192.0.5
  asNumber: 64512
EOF
""", shell=True)

    def tearDown(self):
        deleted_stuff = False
        try:
            subprocess.check_call("docker rm -f kube-node-extra", shell=True)
        except subprocess.CalledProcessError:
            deleted_stuff = True
        try:
            subprocess.check_call("kubectl delete ns bgp-test", shell=True)
        except subprocess.CalledProcessError:
            deleted_stuff = True
        if deleted_stuff:
            sleep(40)

    def test_bgp_advert(self):
        """
        Test that BGP routes to services are exported over BGP
        """

        # # Test access to nginx svc from kube-node-extra
        sleep(30)
        subprocess.check_call("docker exec kube-node-extra ip r", shell=True)
        # Assert that a route to the service IP range is present
        subprocess.check_call("docker exec kube-node-extra ip r | grep 10.96.0.0/12", shell=True)
        # Assert that the nginx service can be curled from the external node
        subprocess.check_call("docker exec kube-node-extra "
                              "curl --connect-timeout 2 -m 3  "
                              "$(kubectl get svc nginx -n bgp-test -o json | jq -r .spec.clusterIP)", shell=True)
