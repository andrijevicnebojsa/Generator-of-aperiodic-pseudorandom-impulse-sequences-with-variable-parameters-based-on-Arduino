// =========================================================
// APPI Generator – firmware za Python GUI (bez Timer1 ISR)
// Komande iz GUI-ja:
//   LAMBDA:<value>;MINW:<value>;MAXW:<value>\n
// Telemetrija ka GUI-ju:
//   Impuls @ <ms> ms | širina: <us> µs | sledeći razmak: <ms> ms
// Pin 8 = izlaz impulsa (TTL)
// =========================================================

#include <Arduino.h>

// Stanje impulsa
bool pulse_active = false;

// Tajmeri u mikrosekundama
unsigned long pulse_start_us = 0;   // kada je impuls krenuo
unsigned long last_event_us = 0;    // poslednji završeni impuls
unsigned long isi_us = 200000;      // početni ISI ~200 ms

// Parametri koje podešava GUI
double lambda_hz = 2.0;             // [Hz]
unsigned int min_width_us = 50;     // [µs]
unsigned int max_width_us = 1000;   // [µs]
unsigned int pulse_width_us = 200;  // trenutna širina [µs]

// =========================================================
// Eksponencijalna raspodela ISI (Poisson proces)
// vraća ISI u mikrosekundama
// =========================================================
unsigned long generate_isi_us(double lambda)
{
    if (lambda <= 0.0) lambda = 0.1;       // zaštita
    double r = (double)random(1, 10001) / 10000.0;   // (0,1]
    double isi_s = -log(r) / lambda;                // eksponencijalna raspodela
    double isi_us_d = isi_s * 1e6;
    if (isi_us_d < 1000.0) isi_us_d = 1000.0;       // min 1 ms da ne „luduje“
    return (unsigned long)isi_us_d;
}

void setup()
{
    Serial.begin(9600);
    pinMode(8, OUTPUT);
    digitalWrite(8, LOW);

    randomSeed(analogRead(A0));

    // inicijalne vrednosti
    pulse_active   = false;
    last_event_us  = micros();
    isi_us         = generate_isi_us(lambda_hz);
}

void loop()
{
    unsigned long now_us = micros();

    // ----------------------------------------------------
    // 1) START NOVOG IMPULSA – kada istekne ISI
    // ----------------------------------------------------
    if (!pulse_active && (now_us - last_event_us >= isi_us))
    {
        // izaberi širinu impulsa
        if (min_width_us > max_width_us) {
            // ako se desio glup parametar, ispravi
            unsigned int tmp = min_width_us;
            min_width_us = max_width_us;
            max_width_us = tmp;
        }

        pulse_width_us = random(min_width_us, max_width_us + 1);

        // start impulsa
        digitalWrite(8, HIGH);
        pulse_active = true;
        pulse_start_us = now_us;

        // izračunaj sledeći ISI (odnosi se na vreme kada se impuls završi)
        isi_us = generate_isi_us(lambda_hz);

        // vreme impulsnog početka u milisekundama za GUI log
        unsigned long t_ms = now_us / 1000UL;
        unsigned long isi_ms = isi_us / 1000UL;

        Serial.print("Impuls @ ");
        Serial.print(t_ms);
        Serial.print(" ms | širina: ");
        Serial.print(pulse_width_us);
        Serial.print(" µs | sledeći razmak: ");
        Serial.print(isi_ms);
        Serial.println(" ms");
    }

    // ----------------------------------------------------
    // 2) ZAVRŠETAK IMPULSA – kada istekne širina
    // ----------------------------------------------------
    if (pulse_active && (now_us - pulse_start_us >= pulse_width_us))
    {
        digitalWrite(8, LOW);
        pulse_active = false;
        last_event_us = now_us;   // ovo vreme je referenca za sledeći ISI
    }

    // ----------------------------------------------------
    // 3) OBRADA KOMANDI IZ PYTHON GUI-ja
    // ----------------------------------------------------
    if (Serial.available())
    {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();

        if (cmd.startsWith("LAMBDA:"))
        {
            int i1 = cmd.indexOf(':');
            int i2 = cmd.indexOf(';');

            if (i1 != -1 && i2 != -1)
                lambda_hz = cmd.substring(i1 + 1, i2).toFloat();

            int j1 = cmd.indexOf("MINW:");
            int j2 = cmd.indexOf(";", j1);
            if (j1 != -1 && j2 != -1)
                min_width_us = cmd.substring(j1 + 5, j2).toInt();

            int k1 = cmd.indexOf("MAXW:");
            if (k1 != -1)
                max_width_us = cmd.substring(k1 + 5).toInt();

            // odmah preračunaj novi ISI da korisnik oseti promenu
            isi_us = generate_isi_us(lambda_hz);

            Serial.print("Parametri primljeni -> λ=");
            Serial.print(lambda_hz, 3);
            Serial.print(" Hz, min=");
            Serial.print(min_width_us);
            Serial.print(" µs, max=");
            Serial.print(max_width_us);
            Serial.println(" µs");
        }
    }
}
