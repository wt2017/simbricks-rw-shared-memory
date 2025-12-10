#!/usr/bin/env python3
"""
Gem5 + ns-3 + External Memory SimBricks experiment script

This script implements a system where gem5 host accesses external memory through ns-3 network.

System architecture:
Application (x86 on gem5) --> gem5 x86 CPU --> Network Interface --> ns-3 Network --> Memory Server --> External Memory

Note: This is a conceptual implementation. The actual memory-over-network mechanism
would require additional components not present in standard SimBricks examples.
"""

from simbricks.orchestration import system
from simbricks.orchestration import simulation as sim
from simbricks.orchestration import instantiation as inst
from simbricks.orchestration.helpers import instantiation as inst_helpers
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import disk_images

# Create empty instantiations list that simbricks-run expects
instantiations = []

print("Creating gem5 + ns-3 + external memory experiment...")
print("System architecture: gem5 host -> ns-3 network -> external memory")
print(f"Shared memory address: 0x3FC0000")
print(f"Shared memory size: 4MB")
print("Expected output: [shared_bmk] PASS: all 1024 bytes match")

# Create system
sys = system.System()

# ============ GEM5 HOST COMPONENTS ============

# Create x86 host (gem5)
host = sys_host.LinuxHost(sys)
host.name = "x86_host"
host.memory = 1024  # 1GB memory
host.cores = 1
host.cpu_freq = "3GHz"

# Add disk images
host.add_disk(system.DistroDiskImage(sys, name="shm-rw"))
host.add_disk(system.LinuxConfigDiskImage(sys, host))

# Create external memory device (would be accessed through network)
external_mem = sys_mem.MemSimpleDevice(sys)
external_mem.name = "external_mem"
external_mem._addr = 0x3FC0000  # Physical address used by shm_rw
external_mem._size = 4 * 1024 * 1024  # 4MB
external_mem._as_id = 0

# Create a memory proxy component in gem5 (to be accessed via network)
class MemoryProxy(sys_mem.MemSimpleDevice):
    def __init__(self, s: system.System):
        super().__init__(s)
        self.name = "memory_proxy"

mem_proxy = MemoryProxy(sys)
mem_proxy._addr = 0x3FC0000
mem_proxy._size = 4 * 1024 * 1024
mem_proxy._as_id = 0

# Create memory interconnect to bridge proxy and external memory
mem_interconnect = sys_mem.MemInterconnect(sys)
mem_interconnect.name = "mem_interconnect"

# Connect the interconnect to the external memory device
interconnect_channel = mem_interconnect.connect_device(external_mem._mem_if)

# Connect the memory proxy to the interconnect using its existing _mem_if
# The connect_device method will handle the interface connection properly
proxy_channel = mem_interconnect.connect_device(mem_proxy._mem_if)

# Add memory route for the external memory device
interconnect_host_if = None
for intf in mem_interconnect.interfaces():
    if isinstance(intf, sys_mem.MemHostInterface):
        interconnect_host_if = intf
        break

if interconnect_host_if:
    mem_interconnect.add_route(
        dev=interconnect_host_if,
        vaddr=0x3FC0000,
        len=4 * 1024 * 1024,
        paddr=0x3FC0000
    )

# ============ NETWORK COMPONENTS FOR NS-3 ============

# Create a network switch (simulated by ns-3)
switch = system.EthSwitch(sys)

# Create first interface on switch for gem5 host
switch_eth_if1 = system.EthInterface(switch)
switch.add_if(switch_eth_if1)

# Create second interface on switch for dummy host
switch_eth_if2 = system.EthInterface(switch)
switch.add_if(switch_eth_if2)

# Create a dummy host (Qemu) to have a complete network topology
dummy_host = sys_host.LinuxHost(sys)
dummy_host.name = "dummy_host"
dummy_host.memory = 512  # 512MB memory
dummy_host.cores = 1
dummy_host.cpu_freq = "2GHz"

# Add disk images to dummy host
dummy_host.add_disk(system.DistroDiskImage(sys, name="base"))
dummy_host.add_disk(system.LinuxConfigDiskImage(sys, dummy_host))

# Create network interface for gem5 host (using a simple NIC)
# Note: Using a simple NIC instead of direct EthInterface for compatibility
gem5_nic = system.IntelI40eNIC(sys)
gem5_nic.add_ipv4("10.0.0.1")

# Create PCIe host interface for gem5 host and connect to gem5 NIC
pcie0 = system.PCIeHostInterface(host)
host.add_if(pcie0)
pcichannel0 = system.PCIeChannel(pcie0, gem5_nic._pci_if)

# Create network interface for dummy host
dummy_nic = system.IntelI40eNIC(sys)
dummy_nic.add_ipv4("10.0.0.2")

# Create PCIe host interface for dummy host and connect to dummy NIC
pcie1 = system.PCIeHostInterface(dummy_host)
dummy_host.add_if(pcie1)
pcichannel1 = system.PCIeChannel(pcie1, dummy_nic._pci_if)

# Connect gem5 NIC to switch interface 1
gem5_channel = system.EthChannel(gem5_nic._eth_if, switch_eth_if1)
gem5_channel.latency = 2 * 10**6  # 2ms latency

# Connect dummy NIC to switch interface 2
dummy_channel = system.EthChannel(dummy_nic._eth_if, switch_eth_if2)
dummy_channel.latency = 2 * 10**6  # 2ms latency

# ============ APPLICATION ============

# Configure shm_rw application on gem5 host
shm_rw_app = sys_host.app.GenericRawCommandApplication(host, [
    "/home/ubuntu/shm_rw_fixed_addr"
])
host.add_app(shm_rw_app)

# Configure dummy application (sleep) on dummy host
sleep_app = system.Sleep(dummy_host, infinite=True)
sleep_app.wait = False
dummy_host.add_app(sleep_app)

# ============ SIMULATION CONFIGURATION ============

simulation = sim.Simulation("shm_rw_gem5_ns3_extmem", sys)
simulation.timeout = 600
simulation.verbose = True

# Configure component mapping

# Gem5 simulator for the host and memory proxy
host_sim = sim.Gem5Sim(simulation)
host_sim.name = "gem5_host_sim"
host_sim.wait_terminate = True
host_sim.add(host)
host_sim.add(mem_proxy)  # Memory proxy runs in same simulator as host

# ns-3 simulator for the network
net_sim = sim.NS3Net(simulation)
net_sim.name = "ns3_net_sim"
net_sim.wait_terminate = True
net_sim.add(switch)
net_sim.global_conf.stop_time = '60s'

# BasicInterconnect simulator for the memory interconnect
interconnect_sim = sim.BasicInterconnect(simulation)
interconnect_sim.name = "mem_interconnect_sim"
interconnect_sim.wait_terminate = True
interconnect_sim.add(mem_interconnect)

# BasicMem simulator for the external memory device
mem_sim = sim.BasicMem(simulation)
mem_sim.name = "external_mem_sim"
mem_sim.wait_terminate = True
mem_sim.add(external_mem)

# Qemu simulator for the dummy host
dummy_host_sim = sim.QemuSim(simulation)
dummy_host_sim.name = "dummy_host_sim"
dummy_host_sim.wait_terminate = True
dummy_host_sim.add(dummy_host)

# NIC simulators for the Intel I40e NICs
gem5_nic_sim = sim.I40eNicSim(simulation)
gem5_nic_sim.add(gem5_nic)

dummy_nic_sim = sim.I40eNicSim(simulation)
dummy_nic_sim.add(dummy_nic)

# ============ INSTANTIATION ============

instantiation = inst_helpers.simple_instantiation(simulation)
fragment = inst.Fragment()
fragment.add_simulators(host_sim, net_sim, interconnect_sim, mem_sim, dummy_host_sim, gem5_nic_sim, dummy_nic_sim)
instantiation.fragments = [fragment]

# Add to instantiations list
instantiations.append(instantiation)

print(f"Experiment created successfully, containing {len(instantiations)} instantiations")
print("NOTE: This is a conceptual implementation.")
print("The memory path uses MemInterconnect (BasicInterconnect) and external memory (BasicMem).")
print("The network path uses ns-3 for network simulation with two hosts (gem5 and dummy).")
print("Memory traffic does not go through ns-3 in this implementation.")
