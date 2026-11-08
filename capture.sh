#!/bin/bash
# Usage: sudo bash capture.sh   (topology must be up). Saves captures/*.pcap plus ping/traceroute/UDP text output.
command -v tcpdump >/dev/null && command -v traceroute >/dev/null || { echo "Run: sudo apt install -y tcpdump traceroute"; exit 1; }
cd "$(dirname "$0")"; mkdir -p captures
pkill -f "[s]nr.py"
ip netns exec r1 tc qdisc del dev r1r2 root 2>/dev/null; ip netns exec r2 tc qdisc del dev r2r1 root 2>/dev/null
for n in client r1 r2 server; do ip -n $n neigh flush all; done   # forces fresh ARP exchanges
# 1) ARP + ICMP + traceroute, seen on the client interface
ip netns exec client tcpdump -U -i c0 -w captures/client_arp_icmp.pcap 2>/dev/null & T1=$!
sleep 1
ip netns exec client ping -c 3 10.10.3.2 > captures/ping.txt
ip netns exec client traceroute -n 10.10.3.2 > captures/traceroute.txt
sleep 1; kill $T1
# 2) UDP request and reply, seen on the client link and on the Router 1 - Router 2 link
for p in "r1 router r1" "r2 router r2" "server server"; do
  read n a <<< "$p"; ip netns exec $n python3 -u snr.py $a > /tmp/snr_$n.log 2>&1 &
done
sleep 1
ip netns exec client tcpdump -U -i c0 -w captures/client_udp.pcap udp 2>/dev/null & T2=$!
ip netns exec r1 tcpdump -U -i r1r2 -w captures/r1r2_udp.pcap udp 2>/dev/null & T3=$!
sleep 1
ip netns exec client python3 snr.py client 3 1 > captures/udp_test.txt
sleep 1; kill $T2 $T3; pkill -f "[s]nr.py"
cp /tmp/snr_r1.log captures/router1.log; cp /tmp/snr_r2.log captures/router2.log; cp /tmp/snr_server.log captures/server.log
chown -R "${SUDO_USER:-root}" captures
echo "Saved to captures/. Open the .pcap files in Wireshark."
