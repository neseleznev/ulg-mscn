
# Managing and Securing Computer Networks

## Assignment 2

Full problem statement could be found at the
[Guy Leduc's website](http://courses.run.montefiore.ulg.ac.be/mscn/2-openflow.html)

Also this repo includes solution for [Openflow Tutorial](http://courses.run.montefiore.ulg.ac.be/mscn/of-tutorial.html)
which is [of_tutorial.py from mininet](https://github.com/mininet/openflow-tutorial/wiki/Create-a-Learning-Switch).
The author's coding style is preserved.

### Creating a topology
(in virtual machine as mininet)
```
$ cd ~/pox
$ mv $(mytree.py_from_your_location) mytree.py
$ mn --custom mytree.py --topo mytree,depth=2,fanout=3,hosts=4 --switch ovsk --mac --controller remote
```

### Starting SDN Controller
```
$ cd ~/pox
$ mv $(mycontrol.py_from_your_location) mycontrol.py
$ ./pox.py log.level --DEBUG my_controller
```

### Draft to compile a report
Major steps<sup>[1](#myfootnote1)</sup>:

#### 1. **mytree.py**
In fact, there are only few lines of code were changed:
    * Add *\_\_init\_\_* (initializer) argument, save it as attribute
    * True/False variable `is_core_switch = depth > 1`
    * `for _ in range(fanout if is_core_switch else hosts):`
        which means, if we deal with the core switch, **fanout** children
        are created else **hosts** children, that's exactly we had to do

#### 2. Monitoring
Code obtained after Openflow tutorial (completed by ourselves as well)
was used as a base to that task.

Periodic tasks scheduling was made using `pox.lib.recoco.Timer` object,
as it recommended by the authors of POX.

**send_stats_request** procedure every 5 seconds sends port stats request
to all switches. **_handle_PortStatsReceived** saves parsed response.
**log_stats** every minute aggregates statistics prints it. However all
of this covered in the code.

Unfortunately, we're not able to resolve host names or get tree topology
inside Controller lifecycle, so implementation hardly depends on
environment variables:
* DEPTH
* FANOUT
* HOSTS
They have the same meaning like in previous part.

#### 3. Filtering
In order to check whether two MAC-addresses belongs to the same tenant,
TenantMatched object is instantiates and passes to Controller.
First of all it parses **'/home/mininet/tenants.cfg'** and assigns to every
MAC-address from the same component unique number. After, when
**is_same_tenant** method is fired, it checks if these addresses has the
same component id.

In case when MAC is not presented in .cfg, it has id -1.

In case when one of given addresses is broadcast (ff:ff:ff:ff:ff:ff) method returns
True.

#### Suggestions

> To send requests at regular intervals, you will likely need to use python threads or timers.

I can imagine what other students might build using timers, especially
if they're not familiar with python (There were lots at OpenFlow practice
lesson). I advocate you to mention Timer, provided by POX developers.
Usage is simple as follows:
```python
# Execute func every 5 seconds
from pox.lib.recoco import Timer
Timer(5, func, recurring=True)
```

________________________________________________________________________
<a name="myfootnote1">1</a>. Follow commit history, to track
step-by-step the way I've solved the task
