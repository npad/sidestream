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
	"sync"
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
var IGNORE_IPV4_NETS = []string{"127.", "128.112.139.", "::ffff:127.0.0.1"}

var SCAMPER_BIN = "/usr/local/bin/scamper"

// ///////////////////////////////////////////////////////////////////////

// Do not traceroute to an IP more than once in this many seconds
var IP_CACHE_TIME_SECONDS = 120

var MAX_CACHE_ENTRY = 1000

type RecentIPCache struct {
	cache map[string]int64
	mu    sync.Mutex
}

func (m *RecentIPCache) New() {
	m = &RecentIPCache{cache: make(map[string]int64, 1000)}
	go func() {
		for now := range time.Tick(time.Second) {
			for k, v := range m.cache {
				if now.Unix()-v > int64(IP_CACHE_TIME_SECONDS) {
					m.mu.Lock()
					delete(m.cache, k)
					m.mu.Unlock()
				}
			}
		}
	}()
	return
}

func (m *RecentIPCache) Len() int {
	return len(m.cache)
}

func (m *RecentIPCache) Add(ip string) {
	_, ok := m.cache[ip]
	if !ok {
		m.mu.Lock()
		if m.cache == nil {
			m.cache = make(map[string]int64, 1000)
		}
		m.cache[ip] = time.Now().Unix()
		m.mu.Unlock()
	}
}

func (m *RecentIPCache) Has(ip string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	_, ok := m.cache[ip]
	return ok
}

var recentIPCache RecentIPCache

// /////////////////////////////////////////////////////////////////////////////

func MakeTestFilename(cookie string) (string, error) {
	stat, err := os.Stat("/proc")
	if err != nil {
		return "", err
	}
	hostname, err := exec.Command("hostname").Output()
	out := string(hostname)
	out = strings.TrimSuffix(out, "\n")
	return fmt.Sprintf("%s_%d_%s", out, stat.ModTime().Unix(), cookie), nil
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
			if recentIPCache.Has(conn.remote_ip) {
				continue
			}
			recentIPCache.Add(conn.remote_ip)
			connectionPool = append(connectionPool, *conn)
			log.Printf("pool add IP: " + conn.remote_ip)
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
	command := exec.Command(SCAMPER_BIN, "-O", "json", "-I", "tracelb -P icmp-echo -q 3 -O ptr "+conn.remote_ip)
	filename, err := MakeTestFilename(conn.cookie)
	if err != nil {
		return
	}
	log.Println("filename: " + filename)

	var outbuf, errbuf bytes.Buffer

	// set the output to our variable
	command.Stdout = &outbuf
	command.Stderr = &errbuf

	err = command.Run()
	if err != nil {
		log.Printf("failed call for: %v", err)
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
	recentIPCache.New()
	pool := GetConnections()
	count := 0
	for true {
		for _, conn := range pool {
			if count > 5 {
				count = 0
				break
			}
			log.Printf("PT start: %s %d", conn.remote_ip, conn.remote_port)
			count++
			go RunScamper(conn)
		}
		time.Sleep(5 * time.Second)
	}
}
