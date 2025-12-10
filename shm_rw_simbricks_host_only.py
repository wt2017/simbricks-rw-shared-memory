#!/usr/bin/env python3
"""
SimBricks experiment script: x86 application running shm_rw on gem5 host-only configuration

System architecture:
Application(x86) --> gem5 x86 CPU --> Local memory system

This script creates a single component:
1. gem5 x86 system running shm_rw application with local memory
"""

from simbricks.orchestration import system
from simbricks.orchestration import simulation as sim
from simbricks.orchestration import instantiation as inst
from simbricks.orchestration.helpers import instantiation as inst_helpers
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import disk_images

# Create empty instantiations list that simbricks-run expects
instantiations = []

print("Creating experiment for x86 application running shm_rw on gem5 host-only configuration...")
print("System architecture: Application(x86) --> gem5 x86 CPU --> Local memory system")
print("Expected output: [shared_bmk] PASS: all 1024 bytes match")

# Create system
sys = system.System()

# Create x86 host
host = sys_host.LinuxHost(sys)
host.name = "x86_host"
host.memory = 1024  # 1GB memory
host.cores = 1
host.cpu_freq = "3GHz"

# Add disk images - using shm-rw image which should contain the shm_rw binary
host.add_disk(system.DistroDiskImage(sys, name="shm-rw"))
host.add_disk(system.LinuxConfigDiskImage(sys, host))

# Configure application - run shm_rw using syscall-based version
# The shm_rw binary should be available in the shm-rw disk image
# GenericRawCommandApplication expects commands list, not binary/args
shm_rw_app = sys_host.app.GenericRawCommandApplication(host, [
    "/home/ubuntu/shm_rw_fixed_addr"  # Use syscall-based version instead of /dev/mem version
])
host.add_app(shm_rw_app)

# Create simulation configuration
simulation = sim.Simulation("shm_rw_gem5_host_only", sys)

# Configure simulation parameters
simulation.timeout = 600  # 30 minutes timeout for full boot and application execution
simulation.verbose = True  # Enable verbose output for debugging

# Configure host sim
host_sim = sim.Gem5Sim(simulation)
host_sim.name = "x86_host_sim"
host_sim.add(host)
host_sim.wait_terminate = True

# Create instantiation
instantiation = inst_helpers.simple_instantiation(simulation)
instantiation.preserve_tmp_folder = True
fragment = inst.Fragment()
fragment.add_simulators(host_sim)
instantiation.fragments = [fragment]


# Add to instantiations list
instantiations.append(instantiation)

print(f"Experiment created successfully, containing {len(instantiations)} instantiations")
print("Configuration: gem5 x86 host running shm_rw application locally")
