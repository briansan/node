import logging
import subprocess
from time import sleep

from kubernetes import client

from tests.k8st.test_base import TestBase

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class TestAllRunning(TestBase):
    def check_pod_status(self, ns):
        pods = self.cluster.list_namespaced_pod(ns)

        for pod in pods.items:
            self.cluster.read_namespaced_pod_status(namespace=ns, name=pod.metadata.name)
            assert pod.status.phase == 'Running'
            _log.debug("%s\t%s\t%s", pod.metadata.name, pod.metadata.namespace, pod.status.phase)

    def test_kubesystem_pods_running(self):
        self.check_pod_status('kube-system')

    def test_default_pods_running(self):
        self.check_pod_status('default')

    def test_calico_monitoring_pods_running(self):
        self.check_pod_status('calico-monitoring')


class TestSimplePolicy(TestBase):
    @classmethod
    def setUpClass(cls):
        cluster = cls.k8s_client()
        cluster.create_namespace(client.V1Namespace(metadata=client.V1ObjectMeta(name="policy-demo")))
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
            namespace="policy-demo")
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
            namespace="policy-demo",
        )
        _log.debug("Service created. status='%s'" % str(api_response.status))

    @classmethod
    def tearDownClass(cls):
        # Delete deployment
        cluster = cls.k8s_client()
        api_response = cluster.delete_namespace(name="policy-demo", body=client.V1DeleteOptions())
        _log.debug("Deployment deleted. status='%s'" % str(api_response.status))
        
    def test_simple_policy(self):
        # Check we can talk to service.
        succeeded = False
        for i in range(5):
            sleep(1)
            if self.check_connected("access"):
                succeeded = True
                break
        assert succeeded is True

        # # Create default-deny policy
        # policy = client.V1NetworkPolicy(
        #     metadata=client.V1ObjectMeta(
        #         name="default-deny",
        #         namespace="policy-demo"
        #     ),
        #     spec={
        #         "podSelector": {
        #             "matchLabels": {},
        #         },
        #     }
        # )
        # client.ExtensionsV1beta1Api().create_namespaced_network_policy(
        #     body=policy,
        #     namespace="policy-demo",
        # )
        # _log.debug("Isolation policy created")
        #
        # # Check we cannot talk to service
        # succeeded = False
        # for i in range(5):
        #     sleep(1)
        #     if not self.check_connected("access"):
        #         succeeded = True
        #         break
        # assert succeeded is True
        #
        # # Create allow policy
        # policy = client.V1NetworkPolicy(
        #     metadata=client.V1ObjectMeta(
        #         name="access-nginx",
        #         namespace="policy-demo"
        #     ),
        #     spec={
        #         'ingress': [{
        #             'from': [{
        #                 'podSelector': {
        #                     'matchLabels': {
        #                         'run': 'access'
        #                     }
        #                 }
        #             }]
        #         }],
        #         'podSelector': {
        #             'matchLabels': {
        #                 'app': 'nginx'
        #             }
        #         }
        #     }
        # )
        # client.ExtensionsV1beta1Api().create_namespaced_network_policy(
        #     body=policy,
        #     namespace="policy-demo",
        # )
        # _log.debug("Allow policy created.")
        #
        # # Check we can talk to service as 'access'
        # succeeded = False
        # for i in range(5):
        #     sleep(1)
        #     if self.check_connected("access"):
        #         succeeded = True
        #         break
        # assert succeeded is True
        #
        # # Check we cannot talk to service as 'cant-access'
        # # Check we cannot talk to service
        # succeeded = False
        # for i in range(5):
        #     sleep(1)
        #     if not self.check_connected("cant-access"):
        #         succeeded = True
        #         break
        # assert succeeded is True

    @staticmethod
    def check_connected(name):
        try:
            subprocess.check_call("kubectl run "
                                  "--namespace=policy-demo "
                                  "%s "
                                  "--restart Never "
                                  "--rm -i "
                                  "--image busybox "
                                  "--command /bin/wget "
                                  "-- -q --timeout=1 nginx" % name,
                                  shell=True)
        except subprocess.CalledProcessError:
            _log.debug("Failed to contact service")
            return False
        _log.debug("Contacted service")
        return True
