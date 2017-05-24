#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This component presents controller for the Task 2 in MSCN ULg course.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpidToStr
from pox.openflow.of_json import flow_stats_to_list

log = core.getLogger()


class Controller(object):
    """
    Majestic class which presents controller, thanks
    duck-typing and disgusting POX architecture
    """
    def __init__(self, connection, tenant_matcher):
        # Keep track of the connection to the switch
        self.connection = connection
        self.tenant_matcher = tenant_matcher

        # This binds listeners _handle_EventType to EventType
        connection.addListeners(self)

        # Use this table to keep track of which ethernet address is on
        # which switch port (keys are MACs, values are ports).
        self.mac_to_port = {}

        # {str(connection.dpid): stats}
        self.statistics = dict()

        # remember the connection dpid for switches
        self.switches = dict()
        self.RX_last = dict()  # {'s1-eth2': 42}
        self.TX_last = dict()

        # timer set to execute every minute
        from pox.lib.recoco import Timer
        # timer set to execute send_stats_request every 5 seconds
        Timer(5, self.send_stats_request, recurring=True)
        # timer set to execute log_stats every minute
        Timer(60, self.log_stats, recurring=True)

        # send first request as soon as possible
        self.send_stats_request()

    @staticmethod
    def send_stats_request():
        """
        Handler for timer function (periodic task) that sends the requests to
        all the switches connected to the controller.
        """
        for connection in core.openflow.connections:
            connection.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        log.debug("Sent %i port stats request(s)", len(core.openflow.connections))

    def resolve_hostname(self, iface):  # Hack
        s = int(iface.split('-')[0][1:])
        eth = int(iface.split('-')[1][3:])
        if s < 2:  # NO_OF leaf switches
            return
        return 'h%d' % (
            (s - 2) * 4  # NO_OF leaf switches, NO_OF leaf hosts
            + eth
        )

    def log_stats(self):
        """
        Handler for timer function (periodic task) that logs statistics
        about switches and hosts:
            * for each switch: the number of dropped packets;
            * for each host: the total number of received and transmitted
              bytes, and the reception and emission bandwidth during
              the last minute.
        """
        for dpid, switch in self.switches.items():
            dropped_count = 0
            for conn in self.statistics[dpid]:
                dropped_count += conn['tx_dropped'] + conn['rx_dropped']
            log.info("%s DROP %d" % (switch['name'], dropped_count))

            for conn in self.statistics[dpid]:
                if conn['port_no'] > 4:  # HACK
                    continue

                iface_name = switch['ports'][conn['port_no']]
                host_name = self.resolve_hostname(iface_name)
                rx, tx = conn['rx_bytes'], conn['tx_bytes']
                if iface_name not in self.RX_last:
                    self.RX_last[iface_name] = 0
                    self.TX_last[iface_name] = 0
                rx_bw = (rx - self.RX_last[iface_name]) / (1000 * 10.0)
                tx_bw = (tx - self.TX_last[iface_name]) / (1000 * 10.0)
                self.RX_last[iface_name] = rx
                self.TX_last[iface_name] = tx

                if host_name:
                    log.info("%s: RX_BYTES %s, TX_BYTES %s, RX_BW %.1f kbps, TX_BW %.1f kbps" % (
                        host_name, rx, tx, rx_bw, tx_bw
                    ))

    def _handle_ConnectionUp(self, event):
        for m in event.connection.features.ports:
            if event.dpid not in self.switches:
                self.switches[event.connection.dpid] = {
                    'name': m.name.split('-')[0],
                    'ports': dict()  # {port_no: 'name'}
                }
                self.RX_last[m.name] = 0
                self.TX_last[m.name] = 0
            self.switches[event.connection.dpid]['ports'][m.port_no] = m.name

    def _handle_PortStatsReceived(self, event):
        """
        Port statistics handler
        :param event: event.stats = statistics received in JSON format
        """
        # dpid = dpidToStr(event.connection.dpid)
        dpid = event.connection.dpid
        stats = flow_stats_to_list(event.stats)
        log.debug("PortStatsReceived from %s: %s", dpid, stats)
        self.statistics[dpid] = stats

    def _handle_PacketIn(self, event):
        """
        Handles packet in messages from the switch.
        """
        packet = event.parsed  # This is the parsed packet data.
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp  # The actual ofp_packet_in message.
        self.act_like_switch(packet, packet_in)

    def resend_packet(self, packet_in, out_port):
        """
        Instructs the switch to resend a packet that it had sent to us.
        "packet_in" is the ofp_packet_in object the switch had sent to the
        controller due to a table-miss.
        """
        msg = of.ofp_packet_out()
        msg.data = packet_in

        # Add an action to send to the specified port
        action = of.ofp_action_output(port=out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)

    def act_like_switch(self, packet, packet_in):
        """
        Implement switch-like behavior.
        """
        # Learn the port for the source MAC
        src, dst, port = packet.src, packet.dst, packet_in.in_port
        self.mac_to_port[src] = port
        log.debug("Wrote mac_to_port[%s] = %s" % (str(src), str(port),))

        if not self.tenant_matcher.is_same_tenant(src, dst):
            log.warning("Attempt to access violation (different tenants)! "
                        "%s -> %s" % (src, dst,))
            return

        if dst.is_multicast or dst not in self.mac_to_port:
            # Flood the packet out everything but the input port
            log.debug("(!) Flooding the packet from %s:%i" % (src, port,))
            self.resend_packet(packet_in, of.OFPP_ALL)
            return

        # The port associated with the destination MAC of the packet is known
        dst_port = self.mac_to_port[dst]

        if dst_port == port:
            log.warning("The same dst_port and port")
            pass  # Do something, dunno what

        # Send packet out the associated port
        # self.resend_packet(packet_in, dst_port)

        log.debug("Installing flow...\n\t[src] %s:%i\t->\t[dst] %s:%i" % (
            src, port, dst, dst_port))

        msg = of.ofp_flow_mod()
        msg.data = packet_in
        # Set fields to match received packet
        msg.match = of.ofp_match.from_packet(packet)

        # Set other fields of flow_mod (timeouts? buffer_id?)
        msg.idle_timeout = 5
        msg.hard_timeout = 15

        # Add an output action, and send -- similar to resend_packet()
        msg.actions.append(of.ofp_action_output(port=dst_port))
        msg.buffer_id = packet_in.buffer_id

        # msg.data = packet_in
        log.debug("Set all fields....")
        self.connection.send(msg)


class TenantMatcher(object):
    def __init__(self, cfg_filename):
        self.mac_to_tenant = dict()

        with open(cfg_filename) as f:
            for idx, line in enumerate(f):
                MACs = line[:-1].split(',')
                for MAC in MACs:
                    self.mac_to_tenant[MAC] = idx

    def is_same_tenant(self, MAC1, MAC2):
        broadcast = of.EthAddr('ff:ff:ff:ff:ff:ff')
        if MAC1 == broadcast or MAC2 == broadcast:
            return True

        tenant1 = self.mac_to_tenant.get(str(MAC1), -1)
        tenant2 = self.mac_to_tenant.get(str(MAC2), -1)
        return tenant1 == tenant2


def launch():
    """
        Starts the component
    """
    # As it was stated in the assignment .cfg is hardcoded
    tenant_matcher = TenantMatcher('/home/mininet/tenants.cfg')

    def handle_connection_up(event):
        log.debug("Controlling %s" % (event.connection,))
        Controller(event.connection, tenant_matcher)
    core.openflow.addListenerByName("ConnectionUp", handle_connection_up)
