import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import nmap
import socket
import ipaddress

class NetworkScan(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.nm = nmap.PortScanner()

    def is_private_ip(self, ip):
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    def resolve_domain(self, target):
        try:
            ip_address = socket.gethostbyname(target)
            if self.is_private_ip(ip_address):
                return None
            return ip_address
        except socket.gaierror:
            return None
    
    async def fetch_dns_records(self, domain, record_type):
        url = f"https://dns.google/resolve?name={domain}&type={record_type}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("Answer", [])
                return None

    def run_nmap_scan(self, target, scan_type):
        resolved_ip = self.resolve_domain(target) or target

        if self.is_private_ip(resolved_ip) or resolved_ip in ["127.0.0.1", "::1", "localhost"]:
            return resolved_ip, "❌ Scanning local or private addresses is not allowed."

        scan_types = {
            "Quick Scan": "-F",
            "Full Scan": "-p-",
            "Service Detection": "-sV"
        }

        if scan_type not in scan_types:
            return resolved_ip, "❌ Invalid scan type."

        try:
            self.nm.scan(resolved_ip, arguments=scan_types[scan_type])
            scan_data = self.nm[resolved_ip]

            results = []
            for port in scan_data.get("tcp", {}):
                service = scan_data["tcp"][port].get("name", "Unknown")
                results.append(f"🟢 **Port {port}** - {service}")

            if scan_type == "OS Detection":
                os_guess = scan_data.get("osmatch", [])
                if os_guess:
                    results.append(f"🖥 **OS Detected:** {os_guess[0]['name']} ({os_guess[0]['accuracy']}% accuracy)")

            return resolved_ip, results if results else None
        except Exception as e:
            return resolved_ip, f"Error running Nmap: {str(e)}"

    @app_commands.command(name="nmap", description="Scan open ports on a target using Nmap")
    @app_commands.describe(
        target="The domain or IP to scan",
        scan_type="Select a scan type"
    )
    @app_commands.choices(scan_type=[
        app_commands.Choice(name="Quick Scan (Fast)", value="Quick Scan"),
        app_commands.Choice(name="Full Scan (All Ports)", value="Full Scan"),
        app_commands.Choice(name="Service Detection (Find Running Services)", value="Service Detection"),
    ])
    async def nmap_scan(self, interaction: discord.Interaction, target: str, scan_type: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True, ephemeral=True)

        resolved_ip, scan_result = self.run_nmap_scan(target, scan_type.value)

        embed = discord.Embed(title=f"🔍 Nmap Scan Results for {target} ({resolved_ip})", color=discord.Color.blue())

        if isinstance(scan_result, str):
            embed.description = scan_result
        elif scan_result:
            embed.add_field(name="🛠 Scan Type", value=scan_type.name, inline=False)
            embed.add_field(name="📡 Scan Results", value="\n".join(scan_result), inline=False)
        else:
            embed.add_field(name="✅ No Open Ports Found", value="Target appears to be secure.", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="checkip", description="Check IP reputation and security info")
    async def check_ip_command(self, interaction: discord.Interaction, ip: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if self.is_private_ip(ip) or ip in ["127.0.0.1", "::1", "localhost"]:
            await interaction.followup.send("❌ Checking private or local IP addresses is not allowed.", ephemeral=True)
            return

        url = f"https://ipinfo.io/{ip}/json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    ip_data = await response.json()
                else:
                    ip_data = None

        if not ip_data:
            await interaction.followup.send("⚠️ Error retrieving IP information.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🌍 IP information for {ip}", color=discord.Color.green())
        embed.add_field(name="📍 Location", value=f"{ip_data.get('city', 'Unknown')}, {ip_data.get('country', 'Unknown')}", inline=False)
        embed.add_field(name="🏢 ISP", value=ip_data.get("org", "Unknown"), inline=False)
        embed.add_field(name="🌎 Hostname", value=ip_data.get("hostname", 'Unknown'), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="reverseip", description="Find all domains hosted on a given IP address")
    async def reverse_ip_command(self, interaction: discord.Interaction, ip: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if self.is_private_ip(ip):
            await interaction.followup.send("❌ Private or local IPs cannot be scanned.", ephemeral=True)
            return

        domains = await self.reverse_ip_lookup(ip)

        embed = discord.Embed(title=f"🔍 Reverse IP Lookup for {ip}", color=discord.Color.blue())

        if domains:
            formatted_domains = "\n".join(domains[:10])
            embed.add_field(name="🌐 Hosted Domains", value=formatted_domains, inline=False)
            embed.set_footer(text="Showing first 10 results. Some results may be omitted.")
        else:
            embed.description = "No domains found for this IP."

        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="dns", description="Retrieve DNS records for a domain")
    async def dns_lookup(self, interaction: discord.Interaction, domain: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        records = {}
        record_types = ["A", "MX", "TXT", "NS", "CNAME"]

        for record_type in record_types:
            records[record_type] = await self.fetch_dns_records(domain, record_type)

        embed = discord.Embed(title=f"📡 DNS Records for {domain}", color=discord.Color.blue())

        for record_type, values in records.items():
            if values:
                record_values = "\n".join([entry.get("data", "Unknown") for entry in values])
                embed.add_field(name=f"🔹 {record_type} Records", value=record_values, inline=False)
            else:
                embed.add_field(name=f"🔹 {record_type} Records", value="❌ No records found.", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(client):
    await client.add_cog(NetworkScan(client))
