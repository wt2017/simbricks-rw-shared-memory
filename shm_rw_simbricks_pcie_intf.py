#!/usr/bin/env python3
"""
Alternative SimBricks experiment script: x86 application accessing external memory through PCIe interface

This script tries a different approach using PCIe interfaces instead of memory interfaces
to avoid gem5's internal memory processing while still achieving external memory access.

System architecture:
Application(x86) --> gem5 x86 CPU --> PCIe interface --> Memory interconnect --> Target memory system
"""

from simbricks.orchestration import system
from simbricks.orchestration import simulation as sim
from simbricks.orchestration import instantiation as inst
from simbricks.orchestration.helpers import instantiation as inst_helpers
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import disk_images
from simbricks.orchestration.system import pcie as sys_pcie

# Create empty instantiations list that simbricks-run expects
instantiations = []

print("Creating alternative experiment using PCIe interface for external memory access...")
print("System architecture: Application(x86) --> gem5 x86 CPU --> PCIe interface --> Memory interconnect")
print(f"Shared memory address: 0x3FC0000")
print(f"Shared memory size: 4MB")
print("Expected output: [shared_bmk] PASS: all 1024 bytes match")

# Create system
sys = system.System()

# Create x86 host
host = sys_host.LinuxHost(sys)
host.name = "x86_host"
host.memory = 1024  # 1GB memory
host.cores = 1
host.cpu_freq = "3GHz"

host.add_disk(system.DistroDiskImage(sys, name="shm-rw"))
host.add_disk(system.LinuxConfigDiskImage(sys, host))

# Create shared memory device
shared_mem = sys_mem.MemSimpleDevice(sys)
shared_mem.name = "shared_mem"
shared_mem._addr = 0x3FC0000  # Physical address used by shm_rw
shared_mem._size = 4 * 1024 * 1024  # 4MB
shared_mem._as_id = 0

# Alternative approach: Use PCIe interface instead of memory interface
# This should avoid gem5's internal memory processing
# Architecture: Host → PCIeHostInterface → PCIeDevice → MemInterconnect → BasicMem

# Create a PCIe device that will connect to the memory interconnect
pcie_mem_device = sys_pcie.PCIeDevice(sys)
pcie_mem_device.name = "pcie_mem_device"

# Create memory interconnect for the PCIe device
mem_interconnect = sys_mem.MemInterconnect(sys)
mem_interconnect.name = "mem_interconnect"

# Connect the interconnect to the memory device
interconnect_channel = mem_interconnect.connect_device(shared_mem._mem_if)

# Connect the PCIe device to the memory interconnect
# This creates a MemHostInterface on the interconnect
pcie_mem_channel = mem_interconnect.connect_host(pcie_mem_device._pcie_if)

# Add memory route for the shared memory device
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

# Create PCIe host interface on the host (this should not trigger memory processing)
pcie_host_if = sys_pcie.PCIeHostInterface(host)
pcie_host_if.name = "pcie_host_if"
host.add_if(pcie_host_if)

# Connect the host PCIe interface to the PCIe memory device
pcie_channel = sys_pcie.PCIeChannel(pcie_host_if, pcie_mem_device._pcie_if)

print(f"PCIe-based memory interconnect created")
print(f"Shared memory device: addr=0x{shared_mem._addr:x}, size={shared_mem._size} bytes")
print(f"PCIe interface will bridge CPU accesses to external memory")

# Configure application
shm_rw_app = sys_host.app.GenericRawCommandApplication(host)
shm_rw_app.binary = "/home/wyou/shm_rw"
shm_rw_app.args = []
host.add_app(shm_rw_app)

# Create simulation configuration
simulation = sim.Simulation("shm_rw_simbricks_pcie_test", sys)
simulation.timeout = 60
simulation.verbose = True

# Configure component mapping
host_sim = sim.Gem5Sim(simulation)
host_sim.name = "x86_host_sim"
host_sim.add(host)

# Create BasicInterconnect for the memory system
interconnect_sim = sim.BasicInterconnect(simulation)
interconnect_sim.name = "mem_interconnect_sim"
interconnect_sim.add(mem_interconnect)

mem_sim = sim.BasicMem(simulation)
mem_sim.name = "shared_mem_sim"
mem_sim.add(shared_mem)

# Create PCIe device simulator (if available)
try:
    pcie_sim = sim.BasicPCIeDevice(simulation)
    pcie_sim.name = "pcie_mem_device_sim"
    pcie_sim.add(pcie_mem_device)
    
    # Create instantiation with PCIe device
    instantiation = inst_helpers.simple_instantiation(simulation)
    fragment = inst.Fragment()
    fragment.add_simulators(host_sim, pcie_sim, interconnect_sim, mem_sim)
    instantiation.fragments = [fragment]
    
except AttributeError:
    print("BasicPCIeDevice not available, trying alternative approach...")
    
    # Try connecting PCIe device to interconnect directly
    # This might work if the interconnect can handle PCIe-to-memory translation
    instantiation = inst_helpers.simple_instantiation(simulation)
    fragment = inst.Fragment()
    fragment.add_simulators(host_sim, interconnect_sim, mem_sim)
    instantiation.fragments = [fragment]

# Add to instantiations list
instantiations.append(instantiation)

print(f"Alternative PCIe-based experiment created successfully, containing {len(instantiations)} instantiations")
