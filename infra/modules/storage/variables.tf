variable "resource_group_name"         { type = string }
variable "location"                    { type = string }
variable "environment"                 { type = string }
variable "private_endpoint_subnet_id"  { type = string }
variable "storage_private_dns_zone_id" { type = string }
variable "tags"                        { type = map(string) }
