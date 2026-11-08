#!/bin/bash
# Usage: sudo bash setup.sh up|down
NS="client r1 r2 server"
if [ "$1" = "down" ]; then
  for n in $NS; do ip netns del $n 2>/dev/null; done; exit 0
fi
set -e
for n in $NS; do ip netns add $n; done
ip link add c0 type veth peer name r1c
ip link add r1r2 type veth peer name r2r1
ip link add r2s type veth peer name s0
ip link set c0 netns client;   ip link set r1c netns r1
ip link set r1r2 netns r1;     ip link set r2r1 netns r2
ip link set r2s netns r2;      ip link set s0 netns server
ip -n client addr add 10.10.1.2/24 dev c0
ip -n r1 addr add 10.10.1.1/24 dev r1c
ip -n r1 addr add 10.10.2.1/24 dev r1r2
ip -n r2 addr add 10.10.2.2/24 dev r2r1
ip -n r2 addr add 10.10.3.1/24 dev r2s
ip -n server addr add 10.10.3.2/24 dev s0
for n in $NS; do ip -n $n link set lo up; done
for p in "client c0" "r1 r1c" "r1 r1r2" "r2 r2r1" "r2 r2s" "server s0"; do
  read ns dev <<< "$p"; ip -n $ns link set $dev up
done
ip -n client route add default via 10.10.1.1
ip -n server route add default via 10.10.3.1
ip -n r1 route add 10.10.3.0/24 via 10.10.2.2
ip -n r2 route add 10.10.1.0/24 via 10.10.2.1
ip netns exec r1 sysctl -qw net.ipv4.ip_forward=1
ip netns exec r2 sysctl -qw net.ipv4.ip_forward=1
