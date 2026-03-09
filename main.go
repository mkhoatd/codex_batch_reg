package main

import (
	"io"
	"log"
	"net/http"
)

func postHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed, use POST", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "failed to read request body", http.StatusInternalServerError)
		return
	}
	defer r.Body.Close()

	log.Printf("Received request body: %s", string(body))

	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("received"))
}

func main() {
	http.HandleFunc("/", postHandler)

	addr := ":8089"
	log.Printf("Server listening on http://localhost%s", addr)

	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
