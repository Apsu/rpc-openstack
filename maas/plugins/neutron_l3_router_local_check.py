#!/usr/bin/env python

# Copyright 2016, Rackspace US, Inc.
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

from __future__ import print_function

from maas_common import get_neutron_client
from maas_common import metric
from maas_common import metric_bool
from maas_common import print_output
from maas_common import status_err
from maas_common import status_ok
from neutronclient.client import exceptions as exc

from pyroute2 import IPDB, NetNS, netns
from netfilter.table import Table

import lxc

# Get a dict of name:data from IPDB interfaces
def _get_interfaces(ipdb, loopback=False):
  return {
    name:data
    for name, data in ipdb.interfaces.items()
    if not isinstance(name, int)
    and (loopback | (name != "lo"))
  }.items()

# Get a list of address,mask tuples from IPDB interface
def _get_addresses(interface, ipv6=False):
  return [
    (addr, mask)
    for addr, mask in interface.ipaddr
    if (ipv6 | (":" not in addr))
  ]

# Get UUID suffix from namespace name
def _get_id_from_ns(namespace):
  # Split at first hyphen
  prefix, uuid = namespace.split("-", 1)
  return uuid

# Convert list to dict, indexed by "id" values
def _to_dict_by_id(array):
  return {v["id"]:v for v in array}

# Dump iptables chains and rules
def _dump_rules(table):
  chains = table.list_chains()
  for chain in chains:
    print("-: {}".format(chain))
    rules = table.list_rules(chain)
    for rule in rules:
      print(">> {}".format(rule.specbits()))

# Check function to run in containers
def _ns_check(neutron):
  # Get all network namespaces
  namespaces = netns.listnetns()
  # Filter Router namespaces
  #dhcps = [n for n in namespaces if "dhcp" in n]
  routers = [r for r in namespaces if "router" in r]

#  # DHCP
#  print("==DHCP Namespaces==")
#
#  # For each DHCP namespace
#  for dhcp in dhcps:
#    print("--{}--".format(dhcp))
#    with NetNS(dhcp) as ns:
#      # iptables
#      for table in ["raw", "filter", "nat", "mangle"]:
#        print(":: Table: {}".format(table))
#        _dump_rules(Table(table))
#      with IPDB(nl=ns) as ip:
#        for name, interface in _get_interfaces(ip):
#          print("Interface: {}, Operstate: {}".format(name, interface.operstate))
#          print("Addresses:")
#          for addr, mask in _get_addresses(interface):
#            print("-> {} / {}".format(addr, mask))

  # Routers
  print("==Router Namespaces==")

  # For each Router namespace
  for router in routers:
    print("--{}--".format(router))
    with NetNS(router) as ns:
      uuid = _get_id_from_ns(router)
      print("UUID: {}".format(uuid))
      # iptables
#      for table in ["raw", "filter", "nat", "mangle"]:
#        print(":: Table: {}".format(table))
#        _dump_rules(Table(table))
      with IPDB(nl=ns) as ip:
        for name, interface in _get_interfaces(ip):
          print("Interface: {}, Operstate: {}".format(name, interface.operstate))
          print("Addresses:")
          for addr, mask in _get_addresses(interface):
            print("-> {} / {}".format(addr, mask))


def check():
    try:
        neutron = get_neutron_client()

    except exc.NeutronClientException:
      # TODO: Do something else here
      pass
    # Any other exception presumably isn't an API error
    except Exception as e:
        status_err(str(e))
    else:
        # Get lists of things
        routers = _to_dict_by_id(neutron.list_routers()['routers'])
        #networks = _to_dict_by_id(neutron.list_networks()['networks'])
        #agents = _to_dict_by_id(neutron.list_agents()['agents'])
        #subnets = _to_dict_by_id(neutron.list_subnets()['subnets'])

        # Check for router conditions
        unscheduled_routers = 0
        inactive_routers = 0
        down_routers = 0
        for uuid, router in routers.items():
          try:
            neutron.list_l3_agent_hosting_routers(uuid)
          except exc.NeutronClientException as e:
            unscheduled_routers += 1
          if router["status"] != "ACTIVE":
            inactive_routers += 1
          if router["admin_state_up"] != True:
            down_routers += 1

        # Get container objects for neutron-agents containers
        containers = [c for c in lxc.list_containers(as_object=True)
                      if "neutron_agents" in c.name and c.state == "RUNNING"]

        # For each matching container
        for container in containers:
          # Attach, run check function, and wait for completion
          container.attach_wait(_ns_check, neutron)

    status_ok()
    metric('neutron_unscheduled_routers',
           'uint32',
           unscheduled_routers,
           'routers')
    metric('neutron_inactive_routers',
           'uint32',
           inactive_routers,
           'routers')
    metric('neutron_down_routers',
           'uint32',
           down_routers,
           'routers')
    #metric_bool('neutron_api_local_status', is_up)
    ## only want to send other metrics if api is up
    #if is_up:
    #    metric('neutron_api_local_response_time',
    #           'double',
    #           '%.3f' % milliseconds,
    #           'ms')
    #    metric('neutron_networks', 'uint32', networks, 'networks')
    #    metric('neutron_agents', 'uint32', agents, 'agents')
    #    metric('neutron_routers', 'uint32', routers, 'agents')
    #    metric('neutron_subnets', 'uint32', subnets, 'subnets')


if __name__ == "__main__":
    with print_output():
        check()
