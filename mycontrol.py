#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This component presents controller for the Task 2 in MSCN ULg course.
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of

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
