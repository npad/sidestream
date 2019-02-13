package main

import (
	"bytes"
	"errors"
	//"fmt"
	"log"
	"net"
	"os/exec"
	"strconv"
	"strings"
)

type Connection struct {
	remote_ip   net.IP
	remote_port int
	local_ip    net.IP
	local_port  int
}

var IGNORE_IPV4_NETS = []string{"127.", "128.112.139."}

func GetHostname() string {
	out, err := exec.Command("hostname").Output()
	if err != nil {
		log.Fatal(err)
	}
	return string(out)
}

func GetConnections() {
	cmd := exec.Command("ss", "-e")
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err != nil {
		log.Fatal(err)
	}

	lines := strings.Split(out.String(), "\n")
	for _, line := range lines {
		var conn Connection
		ParseSSLine(line, &conn)
	}
}

func ParseIPAndPort(input string) (net.IP, int, error) {
	seperator := strings.LastIndex(input, ":")
	if seperator == -1 {
		return net.IP{}, 0, errors.New("cannot parse IP and port correctly")
	}
	IPStr := input[0:seperator]
	if IPStr[0] == '[' {
		IPStr = IPStr[1 : len(IPStr)-1]
	}
	for _, prefix := range IGNORE_IPV4_NETS {
		if strings.HasPrefix(IPStr, prefix) {
			return net.IP{}, 0, errors.New("ignore this IP address")
		}
	}
	outputIP := net.ParseIP(IPStr)
	if outputIP == nil {
		return net.IP{}, 0, errors.New("invalid IP address")
	}

	port, err := strconv.Atoi(input[seperator+1:])
	if err != nil {
		return net.IP{}, 0, errors.New("invalid IP port")
	}
	return outputIP, port, nil
}

// One line of ss output has format like:
// Netid  State      Recv-Q Send-Q                  Local Address:Port                                   Peer Address:Port
func ParseSSLine(line string, output *Connection) error {
	segments := strings.Fields(line)
	log.Printf("length of segs: %d", len(segments))
	log.Println(line)
	if len(segments) < 6 {
		return errors.New("Incomplete line")
	}
	if segments[0] != "tcp" || segments[1] != "ESTAB" {
		return errors.New("not a TCP connection")
	}
	localIP, localPort, err := ParseIPAndPort(segments[4])
	if err != nil {
		return err
	}

	remoteIP, remotePort, err := ParseIPAndPort(segments[5])
	if err != nil {
		return err
	}
	output = &Connection{remote_ip: remoteIP, remote_port: remotePort, local_ip: localIP, local_port: localPort}
	log.Println(output)
	return nil
}

func main() {
	GetConnections()

}
