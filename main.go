package main

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
	//"github.com/m-lab/go/uuid"
)

type Connection struct {
	remote_ip   string
	remote_port int
	local_ip    string
	local_port  int
	cookie      string
}

// The new test output filename is joint of hostname, server boot time, and socker TCO cookie.
// like: pboothe2.nyc.corp.google.com_1548788619_00000000000084FF
var IGNORE_IPV4_NETS = []string{"127.", "128.112.139."}

// Base source port to use when running traceroute
var PARIS_TRACEROUTE_SOURCE_PORT_BASE = 33457

var SCAMPER_BIN = "/usr/local/bin/scamper"

func MakeTestFilename(cookie string) (string, error) {
	stat, err := os.Stat("/proc")
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s_%d_%s", os.Hostname, stat.ModTime().Unix(), cookie), nil
}

func GetConnections() []Connection {
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
	var connectionPool []Connection
	for _, line := range lines {
		conn, err := ParseSSLine(line)
		if err == nil {
			connectionPool = append(connectionPool, *conn)
		}
	}
	return connectionPool
}

func ParseIPAndPort(input string) (string, int, error) {
	seperator := strings.LastIndex(input, ":")
	if seperator == -1 {
		return "", 0, errors.New("cannot parse IP and port correctly")
	}
	IPStr := input[0:seperator]
	if IPStr[0] == '[' {
		IPStr = IPStr[1 : len(IPStr)-1]
	}
	for _, prefix := range IGNORE_IPV4_NETS {
		if strings.HasPrefix(IPStr, prefix) {
			return "", 0, errors.New("ignore this IP address")
		}
	}
	outputIP := net.ParseIP(IPStr)
	if outputIP == nil {
		return "", 0, errors.New("invalid IP address")
	}

	port, err := strconv.Atoi(input[seperator+1:])
	if err != nil {
		return "", 0, errors.New("invalid IP port")
	}
	return IPStr, port, nil
}

func ParseCookie(input string) (string, error) {
	if !strings.HasPrefix(input, "sk:") {
		return "", errors.New("no cookie")
	}
	return input[3:], nil
}

// One line of ss output has format like:
// Netid  State      Recv-Q Send-Q                  Local Address:Port                                   Peer Address:Port
func ParseSSLine(line string) (*Connection, error) {
	segments := strings.Fields(line)
	if len(segments) < 6 {
		return nil, errors.New("Incomplete line")
	}
	if segments[0] != "tcp" || segments[1] != "ESTAB" {
		return nil, errors.New("not a TCP connection")
	}
	localIP, localPort, err := ParseIPAndPort(segments[4])
	if err != nil {
		return nil, err
	}

	remoteIP, remotePort, err := ParseIPAndPort(segments[5])
	if err != nil {
		return nil, err
	}

	cookie, err := ParseCookie(segments[8])
	if err != nil {
		return nil, err
	}

	output := &Connection{remote_ip: remoteIP, remote_port: remotePort, local_ip: localIP, local_port: localPort, cookie: cookie}
	log.Println(output)
	return output, nil
}

func RunScamper(conn Connection) {
	tracelbString := "tracelb -P icmp-echo -q 3 -O ptr " + conn.remote_ip

	command := exec.Command(SCAMPER_BIN, "-O", "json", "-I", tracelbString)
	filename, err := MakeTestFilename(conn.cookie)
	if err != nil {
		return
	}
	log.Println(filename)

	var outbuf, errbuf bytes.Buffer

	// set the output to our variable
	command.Stdout = &outbuf
	command.Stderr = &errbuf

	err = command.Run()
	if err != nil {
		log.Printf("failed call: %v", err)
		return
	}

	ws := command.ProcessState.Sys().(syscall.WaitStatus)
	exitCode := ws.ExitStatus()

	if exitCode != 0 {
		log.Printf("call not exit correctly")
		return
	}

	filepath := "./scamper_output/" + filename

	f, err := os.Create(filepath)
	if err != nil {
		return
	}
	defer f.Close()
	w := bufio.NewWriter(f)
	n, err := w.WriteString(outbuf.String())
	if err != nil {
		return
	}
	fmt.Printf("wrote %d bytes\n", n)
	w.Flush()
}

func main() {
	pool := GetConnections()
	for true {
		for _, conn := range pool {
			log.Printf("PT start: %s %d %s %d", conn.remote_ip, conn.remote_port, conn.local_ip, conn.local_port)
			go RunScamper(conn)
		}
		time.Sleep(5 * time.Second)
	}
}
