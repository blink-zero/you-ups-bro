
# ESXi and QNAP NAS Graceful Shutdown Script

This script monitors the UPS status using NUT (Network UPS Tool) and performs a graceful shutdown of VMs on ESXi hosts, followed by shutting down the ESXi hosts and QNAP NAS devices if the UPS has been on battery for a specified amount of time.

## Prerequisites

- Python 3.x
- Required Python libraries:
  - `requests`
  - `paramiko`
  - `pyvmomi`
- NUT (Network UPS Tool) configured and running on the Raspberry Pi
- VMware ESXi hosts with VMs to be shut down
- QNAP NAS devices to be shut down

## Installation

1. Install the required Python libraries:
   ```sh
   pip install requests paramiko pyvmomi
   ```

2. Ensure NUT is installed and configured on your Raspberry Pi.

## Configuration

Edit the script to set the appropriate configuration values:

- `UPS_STATUS_COMMAND`: Command to check the UPS status.
- `DISCORD_WEBHOOK_URL`: URL for the Discord webhook to send notifications.
- `ESXI_HOSTS`: List of ESXi host IPs or hostnames.
- `ESXI_USER`: Username for ESXi.
- `ESXI_PASS`: Password for ESXi.
- `QNAP_HOSTS`: List of QNAP NAS hostnames.
- `QNAP_USER`: Username for QNAP NAS.
- `QNAP_PASS`: Password for QNAP NAS.
- `SHUTDOWN_DELAY`: Delay (in seconds) before initiating the shutdown sequence when the UPS is on battery.
- `CHECK_INTERVAL`: Interval (in seconds) for checking the UPS status.

## Usage

1. Run the script on the Raspberry Pi:
   ```sh
   python3 shutdown_script.py
   ```

2. The script will:
   - Continuously monitor the UPS status.
   - Wait for 5 minutes if the UPS is on battery.
   - If the UPS remains on battery after the delay, initiate the shutdown sequence.
   - Shutdown VMs on all ESXi hosts concurrently.
   - Shutdown ESXi hosts sequentially.
   - Shutdown QNAP NAS devices.

## Script Details

```python
import time
import subprocess
import requests
import paramiko
import threading
from pyVim.connect import SmartConnect, Disconnect, SmartConnectNoSSL
from pyVmomi import vim

# Configuration
UPS_STATUS_COMMAND = "upsc your-ups@localhost"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_url"
ESXI_HOSTS = ["esxi_ip_1", "exsi_ip_2"]  # Replace with actual IPs or hostnames
ESXI_USER = "your_esxi_username"
ESXI_PASS = "your_esxi_password"
QNAP_HOSTS = ["qnap_host_1", "qnap_host_2"]
QNAP_USER = "your_qnap_username"
QNAP_PASS = "your_qnap_password"
SHUTDOWN_DELAY = 300  # 5 minutes
CHECK_INTERVAL = 60   # 1 minute

def send_discord_notification(message):
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except requests.RequestException as e:
        print(f"Failed to send Discord notification: {e}")

def check_ups_status():
    try:
        result = subprocess.check_output(UPS_STATUS_COMMAND, shell=True).decode('utf-8')
        if "ups.status: OB" in result:
            return "on_battery"
        return "online"
    except subprocess.CalledProcessError as e:
        send_discord_notification(f"Error checking UPS status: {e}")
        return "error"

def are_all_vms_powered_off(content):
    for datacenter in content.rootFolder.childEntity:
        for vm in datacenter.vmFolder.childEntity:
            if isinstance(vm, vim.VirtualMachine):
                if not vm.name.startswith("vCLS") and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                    return False
    return True

def get_host_ip(host):
    for net in host.config.network.vnic:
        return net.spec.ip.ipAddress

def shutdown_esxi_vms(host):
    try:
        si = SmartConnectNoSSL(host=host, user=ESXI_USER, pwd=ESXI_PASS)
        content = si.RetrieveContent()

        # Shut down VMs
        for datacenter in content.rootFolder.childEntity:
            for vm in datacenter.vmFolder.childEntity:
                if isinstance(vm, vim.VirtualMachine):
                    if not vm.name.startswith("vCLS") and vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
                        vm.ShutdownGuest()
                        send_discord_notification(f"Shutdown guest OS on VM {vm.name} on host {host}")

        # Wait for VMs to power off
        while not are_all_vms_powered_off(content):
            send_discord_notification(f"Waiting for VMs to power off on host {host}")
            time.sleep(60)  # Check every minute
        send_discord_notification(f"All VMs are powered off on host {host}")

        Disconnect(si)
    except Exception as e:
        send_discord_notification(f"Error shutting down VMs on ESXi host {host}: {e}")

def shutdown_esxi_hosts():
    for host in ESXI_HOSTS:
        try:
            si = SmartConnectNoSSL(host=host, user=ESXI_USER, pwd=ESXI_PASS)
            content = si.RetrieveContent()

            # Shutdown ESXi host
            host_shut_down = False
            for datacenter in content.rootFolder.childEntity:
                for hostFolder in datacenter.hostFolder.childEntity:
                    if isinstance(hostFolder, vim.ComputeResource) or isinstance(hostFolder, vim.ClusterComputeResource):
                        for esxi_host in hostFolder.host:
                            host_ip = get_host_ip(esxi_host)
                            send_discord_notification(f"Checking host {host_ip} against {host}")
                            if host_ip == host:
                                send_discord_notification(f"Initiating shutdown for ESXi host {esxi_host.name}")
                                try:
                                    task = esxi_host.ShutdownHost_Task(force=True)
                                    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                                        time.sleep(1)
                                    if task.info.state == vim.TaskInfo.State.success:
                                        send_discord_notification(f"ESXi host {esxi_host.name} shutdown successfully")
                                        host_shut_down = True
                                    else:
                                        send_discord_notification(f"Failed to shut down ESXi host {esxi_host.name}: {task.info.error}")
                                except Exception as e:
                                    send_discord_notification(f"Error initiating shutdown for ESXi host {esxi_host.name}: {e}")
            if not host_shut_down:
                send_discord_notification(f"ESXi host {host} was not found in the inventory or could not be shut down")

            Disconnect(si)
        except Exception as e:
            send_discord_notification(f"Error shutting down ESXi host {host}: {e}")

def shutdown_qnap_nas():
    for host in QNAP_HOSTS:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=QNAP_USER, password=QNAP_PASS)
            ssh.exec_command('halt')
            send_discord_notification(f"Shutdown QNAP NAS {host}")
            ssh.close()
        except Exception as e:
            send_discord_notification(f"Error shutting down QNAP NAS {host}: {e}")

def main():
    while True:
        ups_status = check_ups_status()
        if ups_status == "on_battery":
            send_discord_notification("UPS is on battery. Waiting 5 minutes before initiating shutdown sequence.")
            time.sleep(SHUTDOWN_DELAY)
            ups_status = check_ups_status()
            if ups_status == "on_battery":
                send_discord_notification("UPS is still on battery. Initiating shutdown sequence.")
                
                # Create threads to shut down VMs on all hosts simultaneously
                threads = []
                for host in ESXI_HOSTS:
                    thread = threading.Thread(target=shutdown_esxi_vms, args=(host,))
                    thread.start()
                    threads.append(thread)

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                # Shut down ESXi hosts sequentially
                shutdown_esxi_hosts()

                # Shut down QNAP NAS devices
                shutdown_qnap_nas()
            else:
                send_discord_notification("UPS is back online. Shutdown sequence aborted.")
        elif ups_status == "online":
            send_discord_notification("UPS is online.")
        else:
            send_discord_notification("Error checking UPS status.")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
```

