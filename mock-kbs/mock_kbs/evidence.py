def generate_snp_report(measurement: str, report_data: str) -> dict:
    return {
        "report_data": report_data[:128].ljust(128, "0"),
        "measurement": measurement[:96].ljust(96, "0"),
        "policy": "00" * 8,
        "platform_version": "Milan-B1",
        "guest_svn": 1,
    }
