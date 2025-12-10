# Copyright 2024 Max Planck Institute for Software Systems, and
# National University of Singapore
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import abc
import math
import pathlib
import shutil
import typing_extensions as tpe

import simbricks.orchestration.simulation.base as sim_base
import simbricks.orchestration.system as system
from simbricks.orchestration.instantiation import base as inst_base
from simbricks.orchestration.system import host as sys_host
from simbricks.orchestration.system import pcie as sys_pcie
from simbricks.orchestration.system import mem as sys_mem
from simbricks.orchestration.system import disk_images
from simbricks.utils import base as utils_base, file as utils_file
from simbricks.orchestration.instantiation import socket as inst_socket


class HostSim(sim_base.Simulator):

    def __init__(self, simulation: sim_base.Simulation, executable: str, name=""):
        super().__init__(simulation=simulation, executable=executable, name=name)
        self._disk_images: dict[
            sys_host.FullSystemHost, list[tuple[disk_images.DiskImage, str]]
        ] = {}

    def toJSON(self) -> dict:
        return super().toJSON()

    @classmethod
    def fromJSON(cls, simulation: sim_base.Simulation, json_obj: dict) -> tpe.Self:
        instance = super().fromJSON(simulation, json_obj)
        instance._disk_images = {}
        return instance

    def full_name(self) -> str:
        return "host." + self.name

    def add(self, host: sys_host.Host):
        super().add(host)

    @abc.abstractmethod
    def supported_image_formats(self) -> list[str]:
        pass

    @abc.abstractmethod
    async def copy_disk_image(
        self, inst: inst_base.Instantiation, disk_image: disk_images.DiskImage, ident: str
    ) -> str:
        pass

    async def prepare(self, inst: inst_base.Instantiation):
        await super().prepare(inst)

        print(f"DEBUG: HostSim.prepare() called for simulator {self.name}")

        full_sys_hosts = self.filter_components_by_type(ty=sys_host.FullSystemHost)
        print(f"DEBUG: Found {len(full_sys_hosts)} FullSystemHost(s)")

        for host in full_sys_hosts:
            print(f"DEBUG: Processing host: {host.name} (ID: {host.id()})")
            print(f"DEBUG: Host has {len(host.disks)} disk(s)")
            
            host_disks = []
            for i, disk in enumerate(host.disks):
                disk_format = disk.find_format(self)
                needs_copy = disk.needs_copy
                
                print(f"DEBUG: Disk {i}:")
                print(f"DEBUG:   - Disk object: {disk}")
                print(f"DEBUG:   - Needs copy: {needs_copy}")
                print(f"DEBUG:   - Format: {disk_format}")
                
                if disk.needs_copy:
                    copy_path = await self.copy_disk_image(inst, disk, f"{host.id()}.{i}")
                    print(f"DEBUG:   - Copy path: {copy_path}")
                    host_disks.append((disk, copy_path))
                else:
                    original_path = disk.path(inst, disk.find_format(self))
                    print(f"DEBUG:   - Original path: {original_path}")
                    host_disks.append((disk, original_path))
            
            self._disk_images[host] = host_disks
            print(f"DEBUG: Finished processing host {host.name}, stored {len(host_disks)} disk entries")
        
        print("DEBUG: HostSim.prepare() completed")

    def supported_socket_types(
        self, interface: system.Interface
    ) -> set[inst_socket.SockType]:
        return {inst_socket.SockType.CONNECT}


class Gem5Sim(HostSim):

    def __init__(self, simulation: sim_base.Simulation):
        super().__init__(
            simulation=simulation, executable="sims/external/gem5/build/X86/gem5"
        )
        self.name = f"Gem5Sim-{self._id}"
        self.cpu_type_cp = "X86KvmCPU"
        self.cpu_type = "TimingSimpleCPU"
        self.extra_main_args: list[str] = []
        self.extra_config_args: list[str] = []
        self._variant: str = "fast"
        self._sys_clock: str = "1GHz"  # TODO: move to system module

    def supports_checkpointing(self) -> bool:
        return True

    def resreq_cores(self) -> int:
        return 1

    def resreq_mem(self) -> int:
        return 1024

    def supported_image_formats(self) -> list[str]:
        return ["raw"]

    def toJSON(self) -> dict:
        json_obj = super().toJSON()
        json_obj["cpu_type_cp"] = self.cpu_type_cp
        json_obj["cpu_type"] = self.cpu_type
        json_obj["extra_main_args"] = self.extra_main_args
        json_obj["extra_config_args"] = self.extra_config_args
        json_obj["_variant"] = self._variant
        json_obj["_sys_clock"] = self._sys_clock
        return json_obj

    @classmethod
    def fromJSON(cls, simulation: sim_base.Simulation, json_obj: dict) -> tpe.Self:
        instance = super().fromJSON(simulation, json_obj)
        instance.cpu_type_cp = utils_base.get_json_attr_top(json_obj, "cpu_type_cp")
        instance.cpu_type = utils_base.get_json_attr_top(json_obj, "cpu_type")
        instance.extra_main_args = utils_base.get_json_attr_top(
            json_obj, "extra_main_args"
        )
        instance.extra_config_args = utils_base.get_json_attr_top(
            json_obj, "extra_config_args"
        )
        instance._variant = utils_base.get_json_attr_top(json_obj, "_variant")
        instance._sys_clock = utils_base.get_json_attr_top(json_obj, "_sys_clock")
        return instance

    async def copy_disk_image(
        self, inst: inst_base.Instantiation, disk_image: disk_images.DiskImage, ident: str
    ):
        return disk_image.path(inst, disk_image.find_format(self))

    async def prepare(self, inst: inst_base.Instantiation) -> None:
        await super().prepare(inst=inst)
        utils_file.mkdir(inst.env.cpdir_sim(sim=self))

    def checkpoint_commands(self) -> list[str]:
        return ["m5 checkpoint"]

    def cleanup_commands(self) -> list[str]:
        return ["m5 exit"]

    def run_cmd(self, inst: inst_base.Instantiation) -> str:
        print(f"DEBUG: Gem5Sim.run_cmd() called for simulator {self.name}")
        print(f"DEBUG: Instantiation: {inst.simulation.name}")
        
        cpu_type = self.cpu_type
        if inst.create_checkpoint:
            cpu_type = self.cpu_type_cp

        full_sys_hosts = self.filter_components_by_type(ty=sys_host.BaseLinuxHost)
        if len(full_sys_hosts) != 1:
            raise Exception("Gem5Sim only supports simulating 1 FullSystemHost")
        host_spec = full_sys_hosts[0]
        
        print(f"DEBUG: Found host: {host_spec.name}")

        cmd = f"{inst.env.repo_base(f'{self._executable}.{self._variant}')} --outdir={inst.env.get_simulator_output_dir(sim=self)} "
        cmd += " ".join(self.extra_main_args)
        cmd += (
            f" {inst.env.repo_base('sims/external/gem5/configs/simbricks/simbricks.py')} --caches --l2cache "
            "--l1d_size=32kB --l1i_size=32kB --l2_size=32MB "
            "--l1d_assoc=8 --l1i_assoc=8 --l2_assoc=16 "
            f"--cacheline_size=64 --cpu-clock={host_spec.cpu_freq}"
            f" --sys-clock={self._sys_clock} "
            f"--checkpoint-dir={inst.env.cpdir_sim(sim=self)} "
            f"--kernel={inst.env.repo_base('images/vmlinux')} "
        )

        assert host_spec in self._disk_images

        # Validate disk image files exist before proceeding
        print(f"DEBUG: Validating disk image files for Gem5Sim...")
        for i, disk in enumerate(self._disk_images[host_spec]):
            disk_path = disk[1]
            print(f"DEBUG: Checking disk {i}: {disk_path}")
            if not pathlib.Path(disk_path).exists():
                print(f"DEBUG: ERROR - Disk file does not exist: {disk_path}")
                raise RuntimeError(f"Gem5Sim disk image file not found: {disk_path}")
            else:
                print(f"DEBUG: Disk file exists: {disk_path}")
                file_size = pathlib.Path(disk_path).stat().st_size
                print(f"DEBUG: Disk file size: {file_size} bytes")

        for disk in self._disk_images[host_spec]:
            cmd += f"--disk-image={disk[1]} "

        cmd += (
            f"--cpu-type={cpu_type} --mem-size={host_spec.memory}MB "
            f"--num-cpus={host_spec.cores} "
            "--mem-type=DDR4_2400_16x4 "
        )

        if host_spec.kcmd_append is not None:
            cmd += f'--command-line-append="{host_spec.kcmd_append}" '

        if inst.create_checkpoint:
            cmd += "--max-checkpoints=1 "

        if inst.restore_checkpoint:
            cmd += "-r 1 "

        fsh_interfaces = host_spec.interfaces()

        # Only calculate latency/sync parameters if there are actual interfaces
        pci_interfaces = system.Interface.filter_by_type(
            interfaces=fsh_interfaces, ty=sys_pcie.PCIeHostInterface
        )
        mem_interfaces = system.Interface.filter_by_type(
            interfaces=fsh_interfaces, ty=sys_mem.MemHostInterface
        )
        
        # Only determine latency/sync if there are interfaces that need them
        print(f"DEBUG: pci_interfaces count: {len(pci_interfaces)}, mem_interfaces count: {len(mem_interfaces)}, channels count: {len(self.get_channels())}")
        if pci_interfaces or mem_interfaces or self.get_channels():
            latency, sync_period, run_sync = (
                sim_base.Simulator.get_unique_latency_period_sync(
                    channels=self.get_channels()
                )
            )
            print(f"DEBUG: Calculated latency={latency}, sync_period={sync_period}, run_sync={run_sync}")
        else:
            # No interfaces means no external communication needed
            latency = sync_period = run_sync = None
            print(f"DEBUG: No PCI or memory interfaces found, skipping latency/sync parameters")

        for inf in pci_interfaces:
            socket = inst.get_socket(interface=inf)
            if socket is None:
                continue
            assert socket._type == inst_socket.SockType.CONNECT
            cmd += (
                f"--simbricks-pci=connect:{socket._path}"
                f":latency={latency}ns"
                f":sync_interval={sync_period}ns"
            )
            if run_sync and not inst.create_checkpoint:
                cmd += ":sync"
            cmd += " "

        for inf in mem_interfaces:
            socket = inst.get_socket(interface=inf)
            if socket is None:
                continue
            assert socket._type == inst_socket.SockType.CONNECT
            utils_base.has_expected_type(inf.component, sys_mem.MemSimpleDevice)
            dev: sys_mem.MemSimpleDevice = inf.component
            cmd += (
                f"--simbricks-mem={dev._size}@{dev._addr}@{dev._as_id}@"
                f"connect:{socket._path}"
                f":latency={latency}ns"
                f":sync_interval={sync_period}ns"
            )
            if run_sync and not inst.create_checkpoint:
                cmd += ":sync"
            cmd += " "

        # Handle MemSimpleDevice components in this simulator (like memory proxy)
        mem_devices = self.filter_components_by_type(ty=sys_mem.MemSimpleDevice)
        print(f"DEBUG: Found {len(mem_devices)} MemSimpleDevice(s) in this simulator")
        for dev in mem_devices:
            # Skip if this device was already processed via a MemHostInterface
            # (though unlikely in this context, we check)
            if any(inf.component is dev for inf in mem_interfaces):
                print(f"DEBUG: Device {dev.name} (id={dev.id()}) already processed via MemHostInterface, skipping")
                continue
            # Get the MemDeviceInterface of the device
            mem_if = dev._mem_if
            print(f"DEBUG: Processing device {dev.name} (id={dev.id()}), addr={dev._addr}, size={dev._size}, as_id={dev._as_id}")
            print(f"DEBUG: MemDeviceInterface id: {mem_if.id()}")
            socket = inst.get_socket(interface=mem_if)
            if socket is None:
                print(f"DEBUG: No socket found for MemDeviceInterface {mem_if.id()}")
                continue
            print(f"DEBUG: Found socket: path={socket._path}, type={socket._type}")
            assert socket._type == inst_socket.SockType.CONNECT
            cmd += (
                f"--simbricks-mem={dev._size}@{dev._addr}@{dev._as_id}@"
                f"connect:{socket._path}"
                f":latency={latency}ns"
                f":sync_interval={sync_period}ns"
            )
            if run_sync and not inst.create_checkpoint:
                cmd += ":sync"
            cmd += " "
            print(f"DEBUG: Added --simbricks-mem flag for device {dev.name}")

        # TODO: FIXME
        # for net in self.net_directs:
        #     cmd += (
        #         '--simbricks-eth-e1000=listen'
        #         f':{env.net2host_eth_path(net, self)}'
        #         f':{env.net2host_shm_path(net, self)}'
        #         f':latency={net.eth_latency}ns'
        #         f':sync_interval={net.sync_period}ns'
        #     )
        #     if cpu_type == 'TimingSimpleCPU':
        #         cmd += ':sync'
        #     cmd += ' '

        cmd += " ".join(self.extra_config_args)

        print(f"DEBUG: Final Gem5 command: {cmd}")
        return cmd


class QemuSim(HostSim):

    def __init__(self, simulation: sim_base.Simulation) -> None:
        super().__init__(
            simulation=simulation,
            executable="sims/external/qemu/build/x86_64-softmmu/qemu-system-x86_64",
        )
        self.name = f"QemuSim-{self._id}"
        self._qemu_img_exec: str = "sims/external/qemu/build/qemu-img"

    def resreq_cores(self) -> int:
        return 1

    def resreq_mem(self) -> int:
        return 1024

    def supported_image_formats(self) -> list[str]:
        return ["qcow2", "raw"]

    def toJSON(self) -> dict:
        json_obj = super().toJSON()
        # disks is created upon invocation of "prepare", hence we do not need to serialize it
        json_obj["qemu_img_exec"] = self._qemu_img_exec
        return json_obj

    @classmethod
    def fromJSON(cls, simulation: sim_base.Simulation, json_obj: dict) -> tpe.Self:
        instance = super().fromJSON(simulation, json_obj)
        instance._qemu_img_exec = utils_base.get_json_attr_top(json_obj, "qemu_img_exec")
        return instance

    async def _make_qcow_copy(
        self, inst: inst_base.Instantiation, disk: disk_images.DiskImage, format: str, ident: str
    ) -> str:
        disk_path = pathlib.Path(disk.path(inst=inst, format=format))
        copy_path = inst.env.img_dir(relative_path=f"hdcopy.{self._id}.{ident}")
        prep_cmds = [
            (
                f"{inst.env.repo_base(relative_path=self._qemu_img_exec)} create -f qcow2 -F qcow2 "
                f'-o backing_file="{disk_path}" '
                f"{copy_path}"
            )
        ]
        await inst._cmd_executor.exec_simulator_prepare_cmds(self, prep_cmds)
        return copy_path

    async def _make_raw_copy(
        self, inst: inst_base.Instantiation, disk: disk_images.DiskImage, format: str, ident: str
    ) -> str:
        disk_path = pathlib.Path(disk.path(inst=inst, format=format))
        copy_path = inst.env.img_dir(relative_path=f"hdcopy.{self._id}.{ident}")
        shutil.copy2(disk_path, copy_path)
        return copy_path

    async def copy_disk_image(
        self, inst: inst_base.Instantiation, disk_image: disk_images.DiskImage, ident: str
    ) -> str:
        format = disk_image.find_format(self)
        if format == "qcow2":
            return await self._make_qcow_copy(inst, disk_image, format, ident)
        else:
            return await self._make_raw_copy(inst, disk_image, format, ident)

    def checkpoint_commands(self) -> list[str]:
        return []

    def cleanup_commands(self) -> list[str]:
        return ["poweroff -f"]

    def run_cmd(self, inst: inst_base.Instantiation) -> str:
        print(f"DEBUG: QemuSim.run_cmd() called for simulator {self.name}")
        
        full_sys_hosts = self.filter_components_by_type(ty=sys_host.BaseLinuxHost)
        if len(full_sys_hosts) != 1:
            raise Exception("QEMU only supports simulating 1 FullSystemHost")
        host_spec = full_sys_hosts[0]
        
        # Only calculate latency/sync parameters if there are actual interfaces
        fsh_interfaces = host_spec.interfaces()
        pci_interfaces = system.Interface.filter_by_type(
            interfaces=fsh_interfaces, ty=sys_pcie.PCIeHostInterface
        )
        
        # Only determine latency/sync if there are interfaces that need them
        if pci_interfaces:
            latency, period, sync = sim_base.Simulator.get_unique_latency_period_sync(
                channels=self.get_channels()
            )
        else:
            # No interfaces means no external communication needed
            latency = period = sync = None
            print(f"DEBUG: No PCI interfaces found, skipping latency/sync parameters")

        accel = ",accel=kvm:tcg" if not sync else ""

        cmd = (
            f"{inst.env.repo_base(relative_path=self._executable)} -machine q35{accel} -serial mon:stdio "
            "-cpu Skylake-Server -display none -nic none "
            f"-kernel {inst.env.repo_base('images/bzImage')} "
        )

        kcmd_append = ""
        if host_spec.kcmd_append is not None:
            kcmd_append = " " + host_spec.kcmd_append

        assert host_spec in self._disk_images
        for index, disk in enumerate(self._disk_images[host_spec]):
            format = disk[0].find_format(self)
            cmd += f"-drive file={disk[1]},if=ide,index={index},media=disk,driver={format} "
        cmd += (
            '-append "earlyprintk=ttyS0 console=ttyS0 root=/dev/sda1 '
            f'init=/home/ubuntu/guestinit.sh rw{kcmd_append}" '
            f"-m {host_spec.memory} -smp {host_spec.cores} "
        )

        if sync:
            unit = host_spec.cpu_freq[-3:]
            if unit.lower() == "ghz":
                base = 0
            elif unit.lower() == "mhz":
                base = 3
            else:
                raise ValueError("cpu frequency specified in unsupported unit")
            num = float(host_spec.cpu_freq[:-3])
            shift = base - int(math.ceil(math.log(num, 2)))

            cmd += f" -icount shift={shift},sleep=off "

        for inf in pci_interfaces:
            socket = inst.get_socket(interface=inf)
            if socket is None:
                continue
            assert socket._type is inst_socket.SockType.CONNECT
            cmd += f"-device simbricks-pci,socket={socket._path}"
            if sync:
                cmd += ",sync=on"
                cmd += f",pci-latency={latency}"
                cmd += f",sync-period={period}"
            else:
                cmd += ",sync=off"
            cmd += " "

        return cmd
