package main

import (
	"bufio"
	"bytes"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
	//"github.com/m-lab/go/uuid"

	"github.com/npad/sidestream/util"
)

var SCAMPER_BIN = "/usr/local/bin/scamper"
var OUTPUT_PATH = "./scamper_output/"

var recentIPCache util.RecentIPCache

type Connection struct {
	remote_ip   string
	remote_port int
	local_ip    string
	local_port  int
	cookie      string
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
	localIP, localPort, err := util.ParseIPAndPort(segments[4])
	if err != nil {
		return nil, err
	}

	remoteIP, remotePort, err := util.ParseIPAndPort(segments[5])
	if err != nil {
		return nil, err
	}

	cookie, err := util.ParseCookie(segments[8])
	if err != nil {
		return nil, err
	}

	output := &Connection{remote_ip: remoteIP, remote_port: remotePort, local_ip: localIP, local_port: localPort, cookie: cookie}
	//log.Println(output)
	return output, nil
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
			log.Printf("Try to add " + conn.remote_ip)
			recentIPCache.Add(conn.remote_ip)
			connectionPool = append(connectionPool, *conn)
			log.Printf("pool add IP: " + conn.remote_ip)
			log.Printf("cache length : %d at %d", recentIPCache.Len(), time.Now().Unix())
		}
	}
	return connectionPool
}

func RunScamper(conn Connection) {
	command := exec.Command(SCAMPER_BIN, "-O", "json", "-I", "tracelb -P icmp-echo -q 3 -O ptr "+conn.remote_ip)
	filename, err := util.MakeTestFilename(conn.cookie)
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

	filepath := util.CreateTimePath(OUTPUT_PATH)
	log.Println(filepath)

	f, err := os.Create(filepath + filename)
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
			if count > 10 {
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
