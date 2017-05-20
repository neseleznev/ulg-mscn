"""Library of potentially useful topologies for Mininet"""

from mininet.topo import Topo


class MyTreeTopo(Topo):
    """Topology for a tree network with a given depth and fanout."""

    def build(self, depth=1, fanout=2, hosts=4):
        # Numbering:  h1..N, s1..M
        self.host_num = 1
        self.switch_num = 1
        # Build topology
        self.add_tree(depth, fanout, hosts)

    def add_tree(self, depth, fanout, hosts):
        """Add a subtree starting with node n.
           depth = tree height
           fanout = number of children for core switches
           hosts = number of children for top-of-rack
           returns: last node added
        """
        is_switch = depth > 0
        is_core_switch = depth > 1

        if is_switch:
            node = self.addSwitch('s%s' % self.switch_num)
            self.switch_num += 1
            for _ in range(fanout if is_core_switch else hosts):
                child = self.add_tree(depth - 1, fanout, hosts)
                self.addLink(node, child)
        else:
            node = self.addHost('h%s' % self.host_num)
            self.host_num += 1
        return node

topos = {'mytree': MyTreeTopo}
