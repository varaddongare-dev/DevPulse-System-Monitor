import warnings
# Force silence all deprecation/future warnings before any packages load
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import platform
import subprocess
import threading
import time
from flask import Flask, render_template, jsonify, request
import psutil
from dotenv import load_dotenv

# Initialize direct NVIDIA NVML driver bindings
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

load_dotenv()
SECURITY_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")

app = Flask(__name__)

# Base cache template for hardware specification properties
CACHED_SPECS = {
    "cpu_model": "Detecting...",
    "gpu_model": "Generic Display Adapter",
    "total_ram": "0 GB",
    "total_disk": "0 GB",
    "os": f"{platform.system()} {platform.release()}"
}

LIVE_GPU_USAGE = 0.0

def initialize_system_specs():
    """Dynamically parses the host machine's exact hardware profile at startup."""
    global CACHED_SPECS, NVML_AVAILABLE
    try:
        # 1. Dynamic NVIDIA GPU Detection
        if NVML_AVAILABLE:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                CACHED_SPECS["gpu_model"] = pynvml.nvmlDeviceGetName(handle)
            except Exception:
                NVML_AVAILABLE = False

        # 2. Windows Environment Deep Querying
        if platform.system() == "Windows":
            try:
                cpu_cmd = 'powershell -Command "(Get-CimInstance Win32_Processor).Name"'
                CACHED_SPECS["cpu_model"] = subprocess.check_output(cpu_cmd, shell=True).decode().strip()
                
                ram_cmd = 'powershell -Command "(Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1).Manufacturer"'
                raw_ram = subprocess.check_output(ram_cmd, shell=True).decode().strip()
                ram_brand = f"{raw_ram} Memory Modules" if (raw_ram and "Unknown" not in raw_ram) else "System Memory"
                
                disk_cmd = 'powershell -Command "(Get-CimInstance Win32_DiskDrive | Where-Object {$_.DeviceID -like \'*PHYSICALDRIVE0*\'}).Model"'
                raw_disk = subprocess.check_output(disk_cmd, shell=True).decode().strip()
                disk_model = raw_disk if raw_disk else "Primary Drive"
                
                # Non-NVIDIA GPU Fallback detection via WMI query
                if not NVML_AVAILABLE:
                    gpu_cmd = 'powershell -Command "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"'
                    raw_gpu = subprocess.check_output(gpu_cmd, shell=True).decode().strip()
                    if raw_gpu:
                        CACHED_SPECS["gpu_model"] = raw_gpu

            except Exception:
                CACHED_SPECS["cpu_model"] = platform.processor()
                ram_brand = "System Memory"
                disk_model = "Storage Drive"
        else:
            CACHED_SPECS["cpu_model"] = platform.processor()
            ram_brand = "System Memory"
            disk_model = "Storage Drive"

        # 3. Dynamic Capacity Computations
        total_ram = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        total_disk = round(psutil.disk_usage('/').total / (1024 ** 3), 1)
        
        CACHED_SPECS["total_ram"] = f"{total_ram} GB ({ram_brand})"
        CACHED_SPECS["total_disk"] = f"{total_disk} GB ({disk_model})"
    except Exception as e:
        print(f"Error initializing static specs: {e}")

def background_gpu_worker():
    """Polls live GPU engine load dynamically if dedicated hardware bindings match."""
    global LIVE_GPU_USAGE
    if not NVML_AVAILABLE:
        return

    while True:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            res = pynvml.nvmlDeviceGetUtilizationRates(handle)
            LIVE_GPU_USAGE = float(res.gpu)
        except Exception:
            LIVE_GPU_USAGE = 0.0
        time.sleep(1)

# Pre-load specifications and execute background thread loops
initialize_system_specs()
if NVML_AVAILABLE:
    gpu_thread = threading.Thread(target=background_gpu_worker, daemon=True)
    gpu_thread.start()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/specs')
def get_specs():
    return jsonify(CACHED_SPECS)


@app.route('/api/stats')
def get_stats():
    """Assembles hardware utilization metrics on demand without blocking."""
    try:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        if cpu_usage is None:
            cpu_usage = 0.0
        ram_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
    except Exception:
        cpu_usage, ram_usage, disk_usage = 0.0, 0.0, 0.0

    global LIVE_GPU_USAGE
    gpu_val = LIVE_GPU_USAGE
    
    # Quick active runtime fallback check if background thread stalls
    if gpu_val == 0.0 and NVML_AVAILABLE:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            res = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_val = float(res.gpu)
        except Exception:
            pass

    processes = []
    try:
        for proc in sorted(psutil.process_iter(['pid', 'name', 'memory_percent']), 
                           key=lambda p: p.info['memory_percent'] or 0, 
                           reverse=True)[:3]:
            processes.append({
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'memory': round(proc.info['memory_percent'] or 0, 2)
            })
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

    return jsonify({
        'cpu': cpu_usage,
        'gpu': gpu_val, 
        'ram': ram_usage,
        'disk': disk_usage,
        'processes': processes
    })


@app.route('/api/ping')
def get_ping():
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', '8.8.8.8']
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)
        if "time=" in output:
            time_str = output.split("time=")[1].split("ms")[0].strip()
            return jsonify({'ping': f"{time_str} ms"})
    except Exception:
        pass
    return jsonify({'ping': 'Timeout/Error'})


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)